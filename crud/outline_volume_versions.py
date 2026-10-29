from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.outline_volume import OutlineVolume
from models.outline_volume_versions import OutlineVolumeVersion
from models.projects import Project


async def add_snapshot(
    db: AsyncSession, volume: OutlineVolume, user_id: int, *, source: str = "manual",
) -> OutlineVolumeVersion:
    latest = await db.scalar(select(func.max(OutlineVolumeVersion.version_number)).where(
        OutlineVolumeVersion.volume_id == volume.id,
    )) or 0
    snapshot = OutlineVolumeVersion(
        project_id=volume.project_id,
        user_id=user_id,
        volume_id=volume.id,
        version_number=latest + 1,
        source=source,
        volume_number=volume.volume_number,
        name=volume.name,
        expected_words=volume.expected_words,
        start_chapter=volume.start_chapter,
        end_chapter=volume.end_chapter,
        outline=volume.outline,
    )
    db.add(snapshot)
    return snapshot


async def list_versions(db: AsyncSession, project_id: int, user_id: int, limit: int = 100):
    result = await db.scalars(
        select(OutlineVolumeVersion)
        .where(OutlineVolumeVersion.project_id == project_id, OutlineVolumeVersion.user_id == user_id)
        .order_by(OutlineVolumeVersion.created_at.desc(), OutlineVolumeVersion.id.desc())
        .limit(max(1, min(limit, 200)))
    )
    return list(result.all())


async def get_version(db: AsyncSession, version_id: int, project_id: int, user_id: int):
    return await db.scalar(select(OutlineVolumeVersion).where(
        OutlineVolumeVersion.id == version_id,
        OutlineVolumeVersion.project_id == project_id,
        OutlineVolumeVersion.user_id == user_id,
    ))


async def restore_version(db: AsyncSession, project: Project, version: OutlineVolumeVersion, user_id: int):
    volume = await db.scalar(select(OutlineVolume).where(
        OutlineVolume.id == version.volume_id,
        OutlineVolume.project_id == project.id,
        OutlineVolume.is_deleted.is_(False),
    ))
    if volume is not None:
        await add_snapshot(db, volume, user_id, source="before_restore")
        volume.name = version.name
        volume.expected_words = version.expected_words
        volume.start_chapter = version.start_chapter
        volume.end_chapter = version.end_chapter
        volume.outline = version.outline
    else:
        max_number = await db.scalar(select(func.max(OutlineVolume.volume_number)).where(
            OutlineVolume.project_id == project.id,
        )) or 0
        volume = OutlineVolume(
            project_id=project.id,
            volume_number=max(max_number + 1, version.volume_number),
            name=version.name,
            expected_words=version.expected_words,
            start_chapter=version.start_chapter,
            end_chapter=version.end_chapter,
            outline=version.outline,
        )
        db.add(volume)
    await db.commit()
    await db.refresh(volume)
    return volume
