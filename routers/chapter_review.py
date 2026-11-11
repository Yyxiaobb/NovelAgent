"""Review preferences and human-in-the-loop chapter review routes."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent import LLMConfigurationError, LLMError
from config.db_conf import get_db
from crud import generation as generation_crud
from crud import projects
from crud import review_preferences as review_preferences_crud
from crud import review_sessions as review_sessions_crud
from models.users import User
from schemas.agent import (
    ChapterGenerationRequest,
    ContentReview,
    ReviewPreferencePayload,
    ReviewSessionApplyRequest,
    ReviewSessionContinueRequest,
    ReviewSessionInfo,
    ReviewSessionSummary,
    RevisionDecision,
)
from services.agent_generation import content_max_tokens as _content_max_tokens
from services.chapter_generation import ContentQualityError, prepare_content_context, validate_content_quality
from services.content_review import (
    is_review_acceptable,
    revise_review_session_once,
    review_runtime_config,
    review_settings,
    summarize_review_jobs,
)
from services.generation_runtime import generation_client, reviewer_client
from utils.auth import get_current_user
from utils.response import success_response


review_router = APIRouter(tags=["agent"])
@review_router.get("/review/config")
async def get_review_config(user: User = Depends(get_current_user)):
    """Expose safe review settings without returning credentials or service URLs."""
    return success_response(message="获取评审配置成功", data=review_runtime_config())


def _review_session_info(session: Any) -> ReviewSessionInfo:
    values = review_sessions_crud.session_values(session)
    if values.get("latest_review"):
        values["latest_review"] = ContentReview.model_validate(values["latest_review"])
    return ReviewSessionInfo.model_validate(values)


async def _persist_manual_review_session(
    db: AsyncSession,
    *,
    user_id: int,
    context: Any,
    payload: ChapterGenerationRequest,
    content: str,
    review_result: Any,
    generation_job_id: str | None = None,
) -> str | None:
    if not review_result or review_result.stop_reason != "manual_approval_required" or not review_result.review:
        return None
    max_rounds, accept_score = review_settings(payload.review_preferences)
    session = await review_sessions_crud.create_session(
        db,
        user_id=user_id,
        project_id=context.project.id,
        chapter_id=context.chapter.id,
        initial_content=review_result.initial_content or content,
        draft_content=content,
        generation_payload=payload.model_dump(mode="json"),
        review_history=[item.as_dict() for item in review_result.history],
        latest_review=review_result.review.model_dump(mode="json"),
        max_rounds=max_rounds,
        accept_score=accept_score,
        generation_job_id=generation_job_id,
    )
    return session.id


@review_router.get("/review/preferences")
async def get_review_preferences(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    record = await review_preferences_crud.get_preferences(db, user.id)
    preferences = review_preferences_crud.preference_values(record)
    return success_response(message="获取评审偏好成功", data={**review_runtime_config(preferences), **preferences})


@review_router.put("/review/preferences")
async def put_review_preferences(
    payload: ReviewPreferencePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = await review_preferences_crud.save_preferences(db, user.id, payload.model_dump(exclude_unset=True))
    preferences = review_preferences_crud.preference_values(record)
    return success_response(message="账户评审偏好已保存", data={**review_runtime_config(preferences), **preferences})


@review_router.get("/projects/{project_id}/review/preferences")
async def get_project_review_preferences(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if await projects.get_project(db, project_id, user.id) is None:
        raise HTTPException(status_code=404, detail="作品不存在或无权访问")
    record = await review_preferences_crud.get_preferences(db, user.id, project_id)
    return success_response(message="获取作品评审偏好成功", data=review_preferences_crud.preference_values(record))


@review_router.put("/projects/{project_id}/review/preferences")
async def put_project_review_preferences(
    project_id: int,
    payload: ReviewPreferencePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if await projects.get_project(db, project_id, user.id) is None:
        raise HTTPException(status_code=404, detail="作品不存在或无权访问")
    record = await review_preferences_crud.save_preferences(
        db, user.id, payload.model_dump(exclude_unset=True), project_id,
    )
    return success_response(message="作品评审偏好已保存", data=review_preferences_crud.preference_values(record))


@review_router.get("/review/stats")
async def get_review_stats(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return review quality and runtime metrics for the signed-in user's work."""
    if project_id is not None and await projects.get_project(db, project_id, user.id) is None:
        raise HTTPException(status_code=404, detail="作品不存在或无权访问")
    jobs = await generation_crud.list_review_jobs(db, user.id, project_id=project_id)
    sessions = await review_sessions_crud.list_review_sessions(db, user.id, project_id=project_id)
    return success_response(message="获取评审统计成功", data=summarize_review_jobs(jobs, sessions))


def _review_session_summary(session: Any) -> ReviewSessionSummary:
    latest_review = session.latest_review if isinstance(session.latest_review, dict) else {}
    latest_score = latest_review.get("overall_score")
    return ReviewSessionSummary(
        id=session.id,
        project_id=session.project_id,
        chapter_id=session.chapter_id,
        generation_job_id=session.generation_job_id,
        status=session.status,
        current_round=session.current_round,
        max_rounds=session.max_rounds,
        accept_score=session.accept_score,
        latest_score=int(latest_score) if isinstance(latest_score, (int, float)) else None,
        stop_reason=session.stop_reason,
        created_at=session.created_at,
        updated_at=session.updated_at,
        completed_at=session.completed_at,
    )


@review_router.get("/review-sessions")
async def list_review_session_history(
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = Query(None, min_length=1, max_length=24),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return bounded review history without loading large draft payloads."""
    if project_id is not None and await projects.get_project(db, project_id, user.id) is None:
        raise HTTPException(status_code=404, detail="作品不存在或无权访问")
    sessions = await review_sessions_crud.list_review_sessions(
        db,
        user.id,
        project_id=project_id,
        chapter_id=chapter_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = await review_sessions_crud.count_review_sessions(
        db,
        user.id,
        project_id=project_id,
        chapter_id=chapter_id,
        status=status,
    )
    return success_response(
        message="获取评审会话列表成功",
        data={
            "items": [_review_session_summary(session) for session in sessions],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@review_router.get("/review-sessions/{session_id}")
async def get_review_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await review_sessions_crud.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="评审会话不存在或无权访问")
    return success_response(message="获取评审会话成功", data=_review_session_info(session))


@review_router.post("/review-sessions/{session_id}/continue")
async def continue_review_session(
    session_id: str,
    payload: ReviewSessionContinueRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await review_sessions_crud.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="评审会话不存在或无权访问")
    if session.last_continue_request_id == payload.request_id and session.last_continue_response:
        return success_response(message="评审修订已完成", data=session.last_continue_response)
    if session.status != "awaiting_review":
        raise HTTPException(status_code=409, detail="评审会话已经结束，不能继续修订")
    if not session.latest_review:
        raise HTTPException(status_code=409, detail="评审会话缺少当前评审结果")
    review = ContentReview.model_validate(session.latest_review)
    issue_ids = {issue.id for issue in review.issues}
    decision_ids = [item.issue_id for item in payload.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise HTTPException(status_code=422, detail="同一评审问题只能选择一次")
    unknown_issue_ids = [item.issue_id for item in payload.decisions if item.issue_id not in issue_ids]
    if unknown_issue_ids:
        raise HTTPException(status_code=422, detail=f"评审问题不存在：{', '.join(unknown_issue_ids)}")
    manual_decisions = [
        RevisionDecision(
            round=session.current_round,
            issue_id=item.issue_id,
            decision=item.decision,
            reason=item.reason,
        )
        for item in payload.decisions
    ]
    request_payload = ChapterGenerationRequest.model_validate(session.generation_payload or {})
    request_payload.review_preferences = {
        **(request_payload.review_preferences.model_dump(exclude_none=True) if request_payload.review_preferences else {}),
        "manual_approval": False,
        "max_rounds": session.max_rounds,
        "accept_score": session.accept_score,
        "enabled": True,
    }
    context = await prepare_content_context(db, session.project_id, session.chapter_id, user.id, request_payload)
    try:
        revised, next_review, agent_decisions = await revise_review_session_once(
            context,
            session.draft_content,
            review,
            generation_client,
            _content_max_tokens,
            lambda value: validate_content_quality(value, context.plan.expected_words),
            manual_decisions=manual_decisions,
            instruction=payload.instruction,
            reviewer_client_factory=reviewer_client,
        )
    except ContentQualityError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL") from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail="评审修订暂时不可用，请稍后重试") from error

    next_round = session.current_round + 1
    next_iteration = {
        "round": next_round,
        "score": next_review.overall_score,
        "review": next_review.model_dump(mode="json"),
    }
    history = [*(session.review_history or []), next_iteration]
    revision_decisions = [*(session.revision_decisions or [])]
    revision_decisions.extend(
        item.model_copy(update={"round": next_round}).model_dump(mode="json") for item in agent_decisions
    )
    manual_history = [*(session.manual_decisions or [])]
    manual_history.extend(item.model_dump(mode="json") for item in manual_decisions)
    accepted = is_review_acceptable(next_review, session.accept_score)
    reached_limit = next_round >= session.max_rounds
    next_status = "completed" if accepted or reached_limit else "awaiting_review"
    stop_reason = "threshold_reached" if accepted else "max_rounds_reached" if reached_limit else "manual_approval_required"
    await review_sessions_crud.save_session(
        db,
        session,
        current_round=next_round,
        draft_content=revised,
        latest_review=next_review.model_dump(mode="json"),
        review_history=history,
        revision_decisions=revision_decisions,
        manual_decisions=manual_history,
        status=next_status,
        stop_reason=stop_reason,
        completed_at=datetime.now() if next_status == "completed" else None,
        last_error=None,
        last_continue_request_id=payload.request_id,
        last_continue_response=None,
    )
    return success_response(message="评审修订已完成", data=_review_session_info(session))


@review_router.post("/review-sessions/{session_id}/apply")
async def apply_review_session(
    session_id: str,
    payload: ReviewSessionApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await review_sessions_crud.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="评审会话不存在或无权访问")
    if session.status not in {"awaiting_review", "completed"}:
        raise HTTPException(status_code=409, detail="当前评审会话不能应用")
    await review_sessions_crud.save_session(
        db,
        session,
        draft_content=payload.content,
        status="applied",
        stop_reason="manual_applied",
        completed_at=datetime.now(),
        last_error=None,
    )
    return success_response(message="评审稿已确认应用", data=_review_session_info(session))
