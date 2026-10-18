from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.generation import GenerationJob


async def get_job(db: AsyncSession, job_id: str, user_id: int) -> GenerationJob | None:
    result = await db.execute(select(GenerationJob).where(GenerationJob.id == job_id, GenerationJob.user_id == user_id))
    return result.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    user_id: int,
    *,
    project_id: int | None = None,
    chapter_id: int | None = None,
    limit: int = 50,
) -> list[GenerationJob]:
    """Return a user's recent generation history, newest first."""
    query = select(GenerationJob).where(GenerationJob.user_id == user_id)
    if project_id is not None:
        query = query.where(GenerationJob.project_id == project_id)
    if chapter_id is not None:
        query = query.where(GenerationJob.chapter_id == chapter_id)
    query = query.order_by(GenerationJob.created_at.desc()).limit(max(1, min(limit, 100)))
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_pending_jobs(db: AsyncSession, *, limit: int = 100) -> list[GenerationJob]:
    """Find jobs that need to be resumed by the application worker."""
    result = await db.execute(
        select(GenerationJob)
        .where(GenerationJob.status.in_(("queued", "running")))
        .order_by(GenerationJob.created_at.asc())
        .limit(max(1, min(limit, 500)))
    )
    return list(result.scalars().all())


async def create_chapter_content_job(
    db: AsyncSession,
    *,
    job_id: str,
    user_id: int,
    project_id: int,
    chapter_id: int,
    payload: dict,
) -> GenerationJob:
    job = GenerationJob(
        id=job_id,
        user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        input_payload=payload,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def update_job(db: AsyncSession, job: GenerationJob, **values) -> GenerationJob:
    for key, value in values.items():
        setattr(job, key, value)
    if values.get("status") in {"completed", "failed", "cancelled"}:
        job.finished_at = datetime.now()
    await db.commit()
    await db.refresh(job)
    return job
