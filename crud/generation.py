from datetime import datetime

from sqlalchemy import select, update
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


async def complete_job_if_active(
    db: AsyncSession,
    job_id: str,
    *,
    output_content: str,
    result: dict,
) -> bool:
    """Complete a job only if a concurrent cancel request did not win."""
    statement = (
        update(GenerationJob)
        .where(GenerationJob.id == job_id, GenerationJob.status != "cancelled")
        .values(
            status="completed", progress=100, output_content=output_content,
            result=result, finished_at=datetime.now(),
        )
    )
    completed = await db.execute(statement)
    await db.commit()
    return completed.rowcount == 1


async def start_job_if_active(db: AsyncSession, job_id: str) -> bool:
    """Claim a queued job without reviving one already cancelled by its owner."""
    started = await db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job_id, GenerationJob.status.in_(("queued", "running")))
        .values(status="running", progress=5)
    )
    await db.commit()
    return started.rowcount == 1
