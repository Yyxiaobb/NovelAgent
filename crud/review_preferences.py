from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.review_preferences import ReviewPreferences


def _scope_query(user_id: int, project_id: int | None):
    query = select(ReviewPreferences).where(ReviewPreferences.user_id == user_id)
    if project_id is None:
        return query.where(ReviewPreferences.project_id.is_(None))
    return query.where(ReviewPreferences.project_id == project_id)


async def get_preferences(db: AsyncSession, user_id: int, project_id: int | None = None) -> ReviewPreferences | None:
    return await db.scalar(_scope_query(user_id, project_id))


async def resolve_preferences(db: AsyncSession, user_id: int, project_id: int) -> dict:
    """Merge account defaults with values explicitly overridden for a project."""
    account = await get_preferences(db, user_id)
    project = await get_preferences(db, user_id, project_id)
    return {**preference_values(account), **preference_values(project)}


async def save_preferences(
    db: AsyncSession,
    user_id: int,
    values: dict,
    project_id: int | None = None,
) -> ReviewPreferences:
    record = await get_preferences(db, user_id, project_id)
    if record is None:
        record = ReviewPreferences(user_id=user_id, project_id=project_id)
        db.add(record)
    for key, value in values.items():
        setattr(record, key, value)
    await db.commit()
    await db.refresh(record)
    return record


def preference_values(record: ReviewPreferences | None) -> dict:
    if record is None:
        return {}
    return {
        key: getattr(record, key)
        for key in ("enabled", "max_rounds", "accept_score", "manual_approval")
        if getattr(record, key) is not None
    }
