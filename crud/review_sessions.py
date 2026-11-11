import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.review_sessions import ReviewSession


async def get_session(db: AsyncSession, session_id: str, user_id: int) -> ReviewSession | None:
    return await db.scalar(
        select(ReviewSession).where(ReviewSession.id == session_id, ReviewSession.user_id == user_id)
    )


async def list_review_sessions(
    db: AsyncSession,
    user_id: int,
    *,
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
    limit: int = 5000,
    offset: int = 0,
) -> list[ReviewSession]:
    query = select(ReviewSession).where(ReviewSession.user_id == user_id)
    if project_id is not None:
        query = query.where(ReviewSession.project_id == project_id)
    if chapter_id is not None:
        query = query.where(ReviewSession.chapter_id == chapter_id)
    if status is not None:
        query = query.where(ReviewSession.status == status)
    result = await db.scalars(
        query.order_by(ReviewSession.created_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 5000)))
    )
    return list(result.all())


async def count_review_sessions(
    db: AsyncSession,
    user_id: int,
    *,
    project_id: int | None = None,
    chapter_id: int | None = None,
    status: str | None = None,
) -> int:
    query = select(func.count()).select_from(ReviewSession).where(ReviewSession.user_id == user_id)
    if project_id is not None:
        query = query.where(ReviewSession.project_id == project_id)
    if chapter_id is not None:
        query = query.where(ReviewSession.chapter_id == chapter_id)
    if status is not None:
        query = query.where(ReviewSession.status == status)
    return int((await db.scalar(query)) or 0)


async def create_session(
    db: AsyncSession,
    *,
    user_id: int,
    project_id: int,
    chapter_id: int,
    initial_content: str,
    draft_content: str,
    generation_payload: dict,
    review_history: list,
    latest_review: dict,
    max_rounds: int,
    accept_score: int,
    generation_job_id: str | None = None,
) -> ReviewSession:
    session = ReviewSession(
        id=uuid.uuid4().hex,
        user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        generation_job_id=generation_job_id,
        initial_content=initial_content,
        draft_content=draft_content,
        generation_payload=generation_payload,
        review_history=review_history,
        latest_review=latest_review,
        max_rounds=max_rounds,
        accept_score=accept_score,
        stop_reason="manual_approval_required",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def save_session(db: AsyncSession, session: ReviewSession, **values) -> ReviewSession:
    for key, value in values.items():
        setattr(session, key, value)
    session.updated_at = datetime.now()
    if values.get("last_continue_request_id") and values.get("last_continue_response") is None:
        response = session_values(session)
        for key in ("created_at", "updated_at", "completed_at"):
            if response.get(key) is not None:
                response[key] = response[key].isoformat()
        session.last_continue_response = response
    await db.commit()
    await db.refresh(session)
    return session


def session_values(session: ReviewSession) -> dict:
    return {
        "id": session.id,
        "project_id": session.project_id,
        "chapter_id": session.chapter_id,
        "status": session.status,
        "current_round": session.current_round,
        "max_rounds": session.max_rounds,
        "accept_score": session.accept_score,
        "initial_content": session.initial_content,
        "draft_content": session.draft_content,
        "latest_review": session.latest_review,
        "review_history": session.review_history or [],
        "revision_decisions": session.revision_decisions or [],
        "manual_decisions": session.manual_decisions or [],
        "stop_reason": session.stop_reason,
        "last_error": session.last_error,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "completed_at": session.completed_at,
    }
