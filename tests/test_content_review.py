import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from schemas.agent import ContentReview, RevisionDecision
from services.chapter_generation import validate_content_quality
from services.content_review import (
    is_review_acceptable,
    parse_revision_output,
    review_content,
    run_review_loop,
    reviewer_model_settings,
    review_runtime_config,
    summarize_review_jobs,
)
from schemas.projects import ChapterPlan


class ContentReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            project=SimpleNamespace(
                project_type="科幻", introduction="星际旅程", outline="追查异常信号",
            ),
            chapter=SimpleNamespace(chapter_number=3),
            plan=ChapterPlan(
                objective="推进故事", conflict="遭遇阻碍", key_events="发现线索",
                ending_hook="留下悬念", expected_words=3000,
            ),
            prompt="创作上下文",
        )
        self.content = "主角沿着异常信号走进废弃空间站，远处传来低沉的回声。" * 30

    def review_json(self, score=90, *, stop=True, must_fix=False):
        return json.dumps({
            "overall_score": score,
            "summary": "整体完成度较好",
            "strengths": ["目标明确"],
            "issues": ([{
                "id": "issue-1", "category": "character", "severity": "major",
                "evidence": "动机过渡略快", "suggestion": "增加心理描写", "must_fix": True,
            }] if must_fix else []),
            "dimension_scores": {
                "goal": score, "continuity": score, "character": score,
                "causality": score, "style": score, "pacing": score, "ending": score,
            },
            "stop_recommendation": stop,
        }, ensure_ascii=False)

    async def test_reviewer_returns_structured_json(self):
        client = SimpleNamespace(achat=AsyncMock(return_value=self.review_json()))
        review = await review_content(self.context, self.content, client)
        self.assertIsInstance(review, ContentReview)
        self.assertEqual(review.overall_score, 90)
        self.assertEqual(client.achat.await_args.kwargs["response_format"], {"type": "json_object"})

    def test_acceptance_requires_threshold_stop_and_no_hard_issue(self):
        good = ContentReview.model_validate(json.loads(self.review_json(90)))
        hard = ContentReview.model_validate(json.loads(self.review_json(95, must_fix=True)))
        self.assertTrue(is_review_acceptable(good, 85))
        self.assertFalse(is_review_acceptable(hard, 85))

    def test_reviewer_settings_are_optional_and_independent(self):
        import os
        previous = {name: os.environ.get(name) for name in ("REVIEW_MODEL", "REVIEW_API_KEY", "REVIEW_BASE_URL")}
        try:
            os.environ["REVIEW_MODEL"] = "review-model"
            os.environ["REVIEW_API_KEY"] = "review-key"
            os.environ["REVIEW_BASE_URL"] = "https://review.test/v1"
            self.assertEqual(reviewer_model_settings(), ("review-model", "review-key", "https://review.test/v1"))
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_review_runtime_config_is_safe_and_reports_incomplete_dedicated_setup(self):
        import os
        previous = {name: os.environ.get(name) for name in (
            "CONTENT_REVIEW_ENABLED", "CONTENT_REVIEW_MAX_ROUNDS", "CONTENT_REVIEW_ACCEPT_SCORE",
            "REVIEW_MODEL", "REVIEW_API_KEY", "REVIEW_BASE_URL",
        )}
        try:
            os.environ["CONTENT_REVIEW_ENABLED"] = "true"
            os.environ["CONTENT_REVIEW_MAX_ROUNDS"] = "2"
            os.environ["CONTENT_REVIEW_ACCEPT_SCORE"] = "88"
            os.environ["REVIEW_MODEL"] = "review-model"
            os.environ.pop("REVIEW_API_KEY", None)
            os.environ["REVIEW_BASE_URL"] = "https://review.test/v1"
            config = review_runtime_config()
            self.assertEqual(config["reviewer_mode"], "dedicated")
            self.assertEqual(config["configuration_status"], "incomplete")
            self.assertEqual(config["accept_score"], 88)
            self.assertNotIn("api_key", config)
            self.assertNotIn("base_url", config)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_review_job_summary_aggregates_scores_decisions_and_durations(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        jobs = [
            SimpleNamespace(
                result={
                    "review_enabled": True, "review_final_score": 80, "review_rounds": 2,
                    "review_stop_reason": "threshold_reached",
                    "revision_decisions": [{"decision": "accepted"}, {"decision": "rejected"}],
                },
                created_at=now - timedelta(seconds=20), finished_at=now,
            ),
            SimpleNamespace(
                result={"review_enabled": True, "review_stop_reason": "review_unavailable"},
                created_at=now - timedelta(seconds=10), finished_at=now,
            ),
            SimpleNamespace(result={"review_enabled": False}, created_at=now, finished_at=None),
        ]
        summary = summarize_review_jobs(jobs)
        self.assertEqual(summary["total_jobs"], 3)
        self.assertEqual(summary["reviewed_jobs"], 2)
        self.assertEqual(summary["average_score"], 80)
        self.assertEqual(summary["review_unavailable_jobs"], 1)
        self.assertEqual(summary["revision_decisions"]["accepted"], 1)

    def test_revision_output_records_acceptance_decisions_and_supports_plain_text_fallback(self):
        structured = json.dumps({
            "content": self.content,
            "revision_decisions": [
                {"issue_id": "issue-1", "decision": "rejected", "reason": "会破坏后续伏笔"},
            ],
        }, ensure_ascii=False)
        content, decisions = parse_revision_output(structured)
        self.assertEqual(content, self.content)
        self.assertEqual(decisions[0].decision, "rejected")
        self.assertIsNone(decisions[0].round)
        plain_content, plain_decisions = parse_revision_output(self.content)
        self.assertEqual(plain_content, self.content)
        self.assertEqual(plain_decisions, [])

    async def test_loop_keeps_best_version_after_revision_scores_lower(self):
        review_outputs = [self.review_json(70, stop=False), self.review_json(80, stop=False)]
        client = SimpleNamespace(
            model="review-model",
            achat=AsyncMock(side_effect=review_outputs),
        )

        @asynccontextmanager
        async def factory():
            yield client

        calls = []

        async def candidate(_client, previous, review):
            calls.append((previous, review.overall_score if review else None))
            return self.content if previous is None else self.content + "修订" * 30

        result = await run_review_loop(
            self.context, factory, candidate,
            lambda value: validate_content_quality(value, 3000),
            max_rounds=2, accept_score=85,
        )
        self.assertEqual(result.stop_reason, "max_rounds_reached")
        self.assertEqual(result.final_score, 80)
        self.assertEqual(result.content, self.content + "修订" * 30)
        self.assertEqual(len(result.history), 2)
        self.assertEqual(calls[0][1], None)
        self.assertEqual(calls[1][1], 70)

    async def test_loop_reports_each_review_iteration_to_persistence_callback(self):
        client = SimpleNamespace(
            model="review-model",
            achat=AsyncMock(side_effect=[self.review_json(90, stop=True)]),
        )

        @asynccontextmanager
        async def factory():
            yield client

        persisted = []

        async def on_iteration(iteration):
            persisted.append(iteration.as_dict())

        async def candidate(_client, previous, review):
            return self.content

        result = await run_review_loop(
            self.context, factory, candidate,
            lambda value: validate_content_quality(value, 3000),
            max_rounds=2, accept_score=85, on_iteration=on_iteration,
        )
        self.assertEqual(result.stop_reason, "threshold_reached")
        self.assertEqual([item["round"] for item in persisted], [1])

    async def test_loop_tags_revision_decisions_with_review_round(self):
        client = SimpleNamespace(
            model="review-model",
            achat=AsyncMock(side_effect=[self.review_json(70, stop=False), self.review_json(90, stop=True)]),
        )

        @asynccontextmanager
        async def factory():
            yield client

        async def candidate(_client, previous, review):
            if previous is None:
                return self.content
            return self.content + "修订" * 30, [RevisionDecision(
                issue_id="issue-1", decision="partially_accepted", reason="保留伏笔",
            )]

        result = await run_review_loop(
            self.context, factory, candidate,
            lambda value: validate_content_quality(value, 3000),
            max_rounds=2, accept_score=85,
        )
        self.assertEqual(result.stop_reason, "threshold_reached")
        self.assertEqual(result.revision_decisions[0].round, 1)

    async def test_manual_approval_returns_after_first_review_without_generating_revision(self):
        client = SimpleNamespace(
            model="review-model",
            achat=AsyncMock(return_value=self.review_json(70, stop=False)),
        )

        @asynccontextmanager
        async def factory():
            yield client

        candidate = AsyncMock(return_value=self.content)
        result = await run_review_loop(
            self.context,
            factory,
            candidate,
            lambda value: validate_content_quality(value, 3000),
            preferences={"manual_approval": True, "max_rounds": 3},
        )

        self.assertEqual(result.stop_reason, "manual_approval_required")
        self.assertEqual(result.rounds, 1)
        self.assertEqual(result.content, self.content)
        candidate.assert_awaited_once_with(client, None, None)


if __name__ == "__main__":
    unittest.main()
