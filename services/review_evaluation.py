"""Deterministic regression evaluation for the editorial review contract."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemas.agent import ContentReview, RevisionDecision


REQUIRED_DIMENSIONS = {
    "goal",
    "continuity",
    "character",
    "causality",
    "style",
    "pacing",
    "ending",
}
DEFAULT_SCORE_DRIFT_TOLERANCE = 5
DEFAULT_DATASET_PATH = Path(__file__).resolve().parent.parent / "evals" / "review_dataset.json"


class ReviewEvaluationError(ValueError):
    """The deterministic review dataset violates the review contract."""


@dataclass(frozen=True)
class ReviewEvaluationSummary:
    dataset_version: str
    case_count: int
    stable_case_count: int
    stability_pass_rate: float
    max_score_drift: int
    decision_count: int
    adopted_decision_count: int
    suggestion_adoption_rate: float | None
    revision_score_samples: int
    improved_revision_count: int
    revision_score_improvement_rate: float | None
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "case_count": self.case_count,
            "stable_case_count": self.stable_case_count,
            "stability_pass_rate": self.stability_pass_rate,
            "max_score_drift": self.max_score_drift,
            "decision_count": self.decision_count,
            "adopted_decision_count": self.adopted_decision_count,
            "suggestion_adoption_rate": self.suggestion_adoption_rate,
            "revision_score_samples": self.revision_score_samples,
            "improved_revision_count": self.improved_revision_count,
            "revision_score_improvement_rate": self.revision_score_improvement_rate,
            "passed": self.passed,
        }


def load_review_dataset(path: str | Path = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    dataset_path = Path(path)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewEvaluationError(f"无法读取评测数据集：{dataset_path}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ReviewEvaluationError("评测数据集必须包含 cases 数组")
    if not payload["cases"]:
        raise ReviewEvaluationError("评测数据集至少需要一个 case")
    return payload


def _parse_review(value: Any, *, case_id: str, label: str) -> ContentReview:
    try:
        review = ContentReview.model_validate(value)
    except ValueError as error:
        raise ReviewEvaluationError(f"评测 case {case_id} 的 {label} 不符合评审结构") from error
    missing = REQUIRED_DIMENSIONS - set(review.dimension_scores)
    if missing:
        raise ReviewEvaluationError(f"评测 case {case_id} 的 {label} 缺少维度：{', '.join(sorted(missing))}")
    return review


def evaluate_review_dataset(
    dataset: dict[str, Any] | None = None,
    *,
    score_drift_tolerance: int = DEFAULT_SCORE_DRIFT_TOLERANCE,
) -> ReviewEvaluationSummary:
    """Evaluate score stability, suggestion adoption, and revision uplift."""
    if score_drift_tolerance < 0:
        raise ReviewEvaluationError("评分漂移容忍度不能小于 0")
    dataset = dataset or load_review_dataset()
    cases = dataset.get("cases") if isinstance(dataset, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ReviewEvaluationError("评测数据集至少需要一个 case")

    stable_case_count = 0
    max_score_drift = 0
    decision_count = 0
    adopted_decision_count = 0
    revision_score_samples = 0
    improved_revision_count = 0
    for raw_case in cases:
        if not isinstance(raw_case, dict) or not isinstance(raw_case.get("id"), str):
            raise ReviewEvaluationError("每个评测 case 必须包含字符串 id")
        case_id = raw_case["id"]
        repeated_reviews = raw_case.get("repeated_reviews")
        if not isinstance(repeated_reviews, list) or len(repeated_reviews) < 2:
            raise ReviewEvaluationError(f"评测 case {case_id} 至少需要两次重复评审")
        parsed_repeated = [
            _parse_review(item, case_id=case_id, label=f"重复评审 {index + 1}")
            for index, item in enumerate(repeated_reviews)
        ]
        scores = [item.overall_score for item in parsed_repeated]
        drift = max(scores) - min(scores)
        max_score_drift = max(max_score_drift, drift)
        if drift <= score_drift_tolerance:
            stable_case_count += 1

        revision = raw_case.get("revision")
        if not isinstance(revision, dict):
            continue
        before = _parse_review(revision.get("before"), case_id=case_id, label="修订前评审")
        after = _parse_review(revision.get("after"), case_id=case_id, label="修订后评审")
        revision_score_samples += 1
        if after.overall_score > before.overall_score:
            improved_revision_count += 1
        issue_ids = {issue.id for issue in before.issues}
        decisions = revision.get("decisions")
        if not isinstance(decisions, list):
            raise ReviewEvaluationError(f"评测 case {case_id} 的修订决策必须是数组")
        for raw_decision in decisions:
            try:
                decision = RevisionDecision.model_validate(raw_decision)
            except ValueError as error:
                raise ReviewEvaluationError(f"评测 case {case_id} 的修订决策结构无效") from error
            if decision.issue_id not in issue_ids:
                raise ReviewEvaluationError(f"评测 case {case_id} 的修订决策引用了未知问题 {decision.issue_id}")
            decision_count += 1
            if decision.decision in {"accepted", "partially_accepted"}:
                adopted_decision_count += 1

    case_count = len(cases)
    return ReviewEvaluationSummary(
        dataset_version=str(dataset.get("version", "unknown")),
        case_count=case_count,
        stable_case_count=stable_case_count,
        stability_pass_rate=round(stable_case_count / case_count, 3),
        max_score_drift=max_score_drift,
        decision_count=decision_count,
        adopted_decision_count=adopted_decision_count,
        suggestion_adoption_rate=(
            round(adopted_decision_count / decision_count, 3) if decision_count else None
        ),
        revision_score_samples=revision_score_samples,
        improved_revision_count=improved_revision_count,
        revision_score_improvement_rate=(
            round(improved_revision_count / revision_score_samples, 3)
            if revision_score_samples
            else None
        ),
        passed=(
            stable_case_count == case_count
            and max_score_drift <= score_drift_tolerance
            and revision_score_samples > 0
            and improved_revision_count == revision_score_samples
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="运行评论员智能体离线回归评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--score-drift-tolerance", type=int, default=DEFAULT_SCORE_DRIFT_TOLERANCE)
    args = parser.parse_args()
    summary = evaluate_review_dataset(
        load_review_dataset(args.dataset),
        score_drift_tolerance=args.score_drift_tolerance,
    )
    print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
