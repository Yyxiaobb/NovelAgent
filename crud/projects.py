from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select

from schemas.projects import ChapterRequest, OutlineRequest, ProjectRequest
from models.projects import Chapter, Project
from crud import versions as chapter_versions
from crud import outline_versions


class ChapterNumberConflictError(Exception):
    """Raised when a project already owns the requested chapter number."""

async def get_projects(db: AsyncSession, user_id: int):
    query = select(Project).where(
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    )
    result = await db.execute(query)
    projects = result.scalars().all()
    return projects


async def get_project(db: AsyncSession, project_id: int, user_id: int):
    query = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def recalculate_project_stats(db: AsyncSession, project: Project, *, lock: bool = False) -> None:
    """Rebuild denormalized chapter and character counts from active chapters."""
    query = select(Chapter).where(
        Chapter.project_id == project.id,
        Chapter.is_deleted.is_(False),
    )
    if lock:
        query = query.with_for_update()
    chapters = list((await db.scalars(query)).all())
    project.chapter_count = len(chapters)
    project.total_words = sum(len(chapter.content or "") for chapter in chapters)

async def create_new_pro(db: AsyncSession, pro_data: ProjectRequest, user_id: int):
    new_pro = Project(
        projectname=pro_data.projectname,
        introduction=pro_data.introduction,
        project_type=pro_data.project_type,
        cover_url=pro_data.cover_url,
        outline=pro_data.outline,
        expected_words=pro_data.expected_words,
        user_id=user_id,
    )
    db.add(new_pro)
    await db.commit()
    await db.refresh(new_pro)
    return new_pro


async def get_project_chapters(db: AsyncSession, project_id: int, user_id: int):
    project_query = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    )
    project_result = await db.execute(project_query)
    if project_result.scalar_one_or_none() is None:
        return None

    query = select(Chapter).join(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
        Chapter.is_deleted.is_(False),
    ).order_by(Chapter.chapter_number, Chapter.id)
    result = await db.execute(query)
    return result.scalars().all()


async def get_chapter(db: AsyncSession, project_id: int, chapter_id: int, user_id: int):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    query = select(Chapter).where(
        Chapter.id == chapter_id,
        Chapter.project_id == project_id,
        Chapter.is_deleted.is_(False),
    )
    return (await db.execute(query)).scalar_one_or_none()


async def get_prior_chapter_memories(db: AsyncSession, project_id: int, chapter_number: int, limit: int = 5):
    query = select(Chapter).where(
        Chapter.project_id == project_id,
        Chapter.chapter_number < chapter_number,
        Chapter.is_deleted.is_(False),
    ).order_by(Chapter.chapter_number.desc(), Chapter.id.desc()).limit(limit)
    result = await db.execute(query)
    return list(reversed(result.scalars().all()))


async def get_story_memory_chapters(db: AsyncSession, project_id: int, chapter_number: int, limit: int = 50):
    """Load a bounded history for cross-chapter continuity memory."""
    query = select(Chapter).where(
        Chapter.project_id == project_id,
        Chapter.chapter_number < chapter_number,
        Chapter.is_deleted.is_(False),
        or_(Chapter.summary.is_not(None), Chapter.memory.is_not(None)),
    ).order_by(Chapter.chapter_number.desc(), Chapter.id.desc()).limit(max(1, min(limit, 200)))
    result = await db.execute(query)
    return list(reversed(result.scalars().all()))


async def update_project(db: AsyncSession, project_id: int, user_id: int, payload: ProjectRequest):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    for field in ("projectname", "introduction", "project_type", "cover_url", "outline", "expected_words", "status"):
        if field in payload.model_fields_set:
            setattr(project, field, getattr(payload, field))
    await db.commit()
    await db.refresh(project)
    return project


async def get_project_outline(db: AsyncSession, project_id: int, user_id: int):
    return await get_project(db, project_id, user_id)


async def update_project_outline(db: AsyncSession, project_id: int, user_id: int, payload: OutlineRequest):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    await outline_versions.add_snapshot(db, project, user_id)
    project.outline = payload.outline
    await db.commit()
    await db.refresh(project)
    return project


async def create_chapter(db: AsyncSession, project_id: int, user_id: int, payload: ChapterRequest):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    project = (await db.execute(
        select(Project).where(Project.id == project.id).with_for_update()
    )).scalar_one()
    existing = await db.scalar(select(Chapter.id).where(
        Chapter.project_id == project.id,
        Chapter.chapter_number == payload.chapter_number,
    ))
    if existing is not None:
        raise ChapterNumberConflictError("该作品已存在此章节编号")
    chapter = Chapter(
        project_id=project.id,
        chapter_number=payload.chapter_number,
        chaptername=payload.chaptername,
        content=payload.content,
        plan=payload.plan.model_dump() if payload.plan is not None else None,
        summary=payload.summary,
        memory=payload.memory.model_dump() if payload.memory is not None else None,
    )
    db.add(chapter)
    await db.flush()
    await recalculate_project_stats(db, project, lock=True)
    await db.commit()
    await db.refresh(chapter)
    return chapter


async def update_chapter(db: AsyncSession, project_id: int, chapter_id: int, user_id: int, payload: ChapterRequest):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    project = (await db.execute(
        select(Project).where(Project.id == project.id).with_for_update()
    )).scalar_one()
    query = select(Chapter).where(
        Chapter.id == chapter_id,
        Chapter.project_id == project_id,
        Chapter.is_deleted.is_(False),
    )
    chapter = (await db.execute(query)).scalar_one_or_none()
    if chapter is None:
        return None
    existing = await db.scalar(select(Chapter.id).where(
        Chapter.project_id == project.id,
        Chapter.chapter_number == payload.chapter_number,
        Chapter.id != chapter.id,
    ))
    if existing is not None:
        raise ChapterNumberConflictError("该作品已存在此章节编号")
    await chapter_versions.add_snapshot(db, chapter, user_id)
    chapter.chapter_number = payload.chapter_number
    chapter.chaptername = payload.chaptername
    chapter.content = payload.content
    if "plan" in payload.model_fields_set:
        chapter.plan = payload.plan.model_dump() if payload.plan is not None else None
    if "summary" in payload.model_fields_set:
        chapter.summary = payload.summary
    if "memory" in payload.model_fields_set:
        chapter.memory = payload.memory.model_dump() if payload.memory is not None else None
    await recalculate_project_stats(db, project, lock=True)
    await db.commit()
    await db.refresh(chapter)
    return chapter
