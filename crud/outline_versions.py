from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.outline_versions import OutlineVersion
from models.projects import Project


async def add_snapshot(db: AsyncSession, project: Project, user_id: int, *, source: str = "manual") -> OutlineVersion:
    result = await db.execute(
        select(func.max(OutlineVersion.version_number)).where(OutlineVersion.project_id == project.id)
    )
    latest = result.scalar_one_or_none() or 0
    snapshot = OutlineVersion(
        project_id=project.id,
        user_id=user_id,
        version_number=latest + 1,
        source=source,
        outline=project.outline,
    )
    db.add(snapshot)
    return snapshot


async def list_versions(db: AsyncSession, project_id: int, user_id: int, limit: int = 50) -> list[OutlineVersion]:
    result = await db.execute(
        select(OutlineVersion)
        .where(OutlineVersion.project_id == project_id, OutlineVersion.user_id == user_id)
        .order_by(OutlineVersion.version_number.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(result.scalars().all())


async def get_version(db: AsyncSession, version_id: int, project_id: int, user_id: int) -> OutlineVersion | None:
    result = await db.execute(
        select(OutlineVersion).where(
            OutlineVersion.id == version_id,
            OutlineVersion.project_id == project_id,
            OutlineVersion.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def restore_version(db: AsyncSession, project: Project, version: OutlineVersion, user_id: int) -> Project:
    await add_snapshot(db, project, user_id, source="before_restore")
    project.outline = version.outline
    await db.commit()
    await db.refresh(project)
    return project
