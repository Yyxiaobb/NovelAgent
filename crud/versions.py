from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.projects import Chapter
from models.versions import ChapterVersion


async def add_snapshot(
    db: AsyncSession,
    chapter: Chapter,
    user_id: int,
    *,
    source: str = "manual",
) -> ChapterVersion:
    result = await db.execute(
        select(func.max(ChapterVersion.version_number)).where(ChapterVersion.chapter_id == chapter.id)
    )
    latest = result.scalar_one_or_none() or 0
    snapshot = ChapterVersion(
        chapter_id=chapter.id,
        project_id=chapter.project_id,
        user_id=user_id,
        version_number=latest + 1,
        source=source,
        chapter_number=chapter.chapter_number,
        chaptername=chapter.chaptername,
        content=chapter.content,
        plan=chapter.plan,
        summary=chapter.summary,
        memory=chapter.memory,
    )
    db.add(snapshot)
    return snapshot


async def list_versions(db: AsyncSession, chapter_id: int, user_id: int, limit: int = 50) -> list[ChapterVersion]:
    result = await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter_id, ChapterVersion.user_id == user_id)
        .order_by(ChapterVersion.version_number.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(result.scalars().all())


async def get_version(db: AsyncSession, version_id: int, chapter_id: int, user_id: int) -> ChapterVersion | None:
    result = await db.execute(
        select(ChapterVersion).where(
            ChapterVersion.id == version_id,
            ChapterVersion.chapter_id == chapter_id,
            ChapterVersion.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def restore_version(
    db: AsyncSession,
    chapter: Chapter,
    version: ChapterVersion,
    user_id: int,
) -> Chapter:
    await add_snapshot(db, chapter, user_id, source="before_restore")
    chapter.chapter_number = version.chapter_number
    chapter.chaptername = version.chaptername
    chapter.content = version.content
    chapter.plan = version.plan
    chapter.summary = version.summary
    chapter.memory = version.memory
    await db.commit()
    await db.refresh(chapter)
    return chapter
