"""Response shaping for persisted generation jobs."""

from __future__ import annotations

from typing import Any

from models.generation import GenerationJob


GENERATION_INFO_KEYS = (
    "model", "prompt_template_id", "prompt_template_version", "segments", "quality_check",
    "review_enabled", "review_rounds", "review_final_score", "review_stop_reason", "review_error",
    "review_history", "revision_decisions", "review_session_id",
)


def generation_info(result: dict | None) -> dict:
    """Keep internal job results out of the public response by allowlisting fields."""
    result = result or {}
    return {key: result[key] for key in GENERATION_INFO_KEYS if result.get(key) is not None}


def generation_job_payload(job: GenerationJob, *, include_scope: bool = False) -> dict[str, Any]:
    """Serialize a job consistently for detail and list endpoints."""
    result = job.result or {}
    payload: dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "content": job.output_content or "",
        "expected_words": result.get("expected_words"),
        "plan": result.get("plan"),
        "citations": result.get("citations", []),
        "generation_info": generation_info(result),
        "error": job.error_message,
    }
    if include_scope:
        payload.update(
            {
                "project_id": job.project_id,
                "chapter_id": job.chapter_id,
                "job_type": job.job_type,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
        )
    return payload
