import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from schemas.agent import ContentReview
from services.chapter_generation import validate_content_quality
from services.content_review import (
    is_review_acceptable,
    review_content,
    run_review_loop,
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


if __name__ == "__main__":
    unittest.main()
