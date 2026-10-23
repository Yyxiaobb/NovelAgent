from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.projects import Chapter, Project
from models.knowledge_base import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from crud.projects import recalculate_project_stats

_NO_PROJECT_STATUS = "未设置"


class ProjectInRecycleBinError(Exception):
    pass


async def move_project_to_recycle_bin(db: AsyncSession, project_id: int, user_id: int):
    query = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    ).with_for_update()
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if project is None:
        return None

    project.previous_status = project.status or _NO_PROJECT_STATUS
    project.status = "回收站"
    await db.commit()
    await db.refresh(project)
    return project


async def get_recycled_projects(db: AsyncSession, user_id: int):
    query = select(Project).where(
        Project.user_id == user_id,
        Project.status == "回收站",
    ).order_by(Project.updated_at.desc(), Project.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


async def _get_recycled_project(db: AsyncSession, project_id: int, user_id: int):
    query = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        Project.status == "回收站",
    ).with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def restore_project(db: AsyncSession, project_id: int, user_id: int):
    project = await _get_recycled_project(db, project_id, user_id)
    if project is None:
        return None

    # 兼容增加 previous_status 字段之前已移入回收站的项目。
    if project.previous_status == _NO_PROJECT_STATUS:
        project.status = None
    elif project.previous_status in ("连载中", "完结", "断更"):
        project.status = project.previous_status
    else:
        project.status = "连载中"
    project.previous_status = None
    await db.commit()
    await db.refresh(project)
    return project


async def permanently_delete_project(db: AsyncSession, project_id: int, user_id: int):
    project = await _get_recycled_project(db, project_id, user_id)
    if project is None:
        return False

    # 使用模型已有的 delete-orphan 级联，在同一事务内删除项目和全部章节。
    await db.delete(project)
    await db.commit()
    return True


async def get_recycled_chapters(db: AsyncSession, user_id: int):
    query = select(Chapter, Project.projectname, Project.status).join(Project).where(
        Project.user_id == user_id,
        Chapter.is_deleted.is_(True),
    ).order_by(Chapter.updated_at.desc(), Chapter.id.desc())
    result = await db.execute(query)
    return result.all()


async def _get_chapter_for_update(
    db: AsyncSession, chapter_id: int, user_id: int, *, is_deleted: bool,
):
    # 与项目删除统一按“项目 -> 章节”加锁，串行化同一作品的章节统计变更。
    project_query = select(Project).where(
        Project.id.in_(select(Chapter.project_id).where(Chapter.id == chapter_id)),
        Project.user_id == user_id,
    ).with_for_update()
    project = (await db.execute(project_query)).scalar_one_or_none()
    if project is None or (not is_deleted and project.status == "回收站"):
        return None

    chapter_query = select(Chapter).where(
        Chapter.id == chapter_id,
        Chapter.project_id == project.id,
        Chapter.is_deleted.is_(is_deleted),
    ).with_for_update()
    chapter = (await db.execute(chapter_query)).scalar_one_or_none()
    return (chapter, project) if chapter is not None else None


async def _update_chapter_count(db: AsyncSession, project: Project):
    # Recalculate both counters from the same locked chapter snapshot.
    await recalculate_project_stats(db, project, lock=True)


async def move_chapter_to_recycle_bin(db: AsyncSession, chapter_id: int, user_id: int):
    match = await _get_chapter_for_update(db, chapter_id, user_id, is_deleted=False)
    if match is None:
        return None

    chapter, project = match
    chapter.is_deleted = True
    await _update_chapter_count(db, project)
    await db.commit()
    await db.refresh(chapter)
    return chapter


async def restore_chapter(db: AsyncSession, chapter_id: int, user_id: int):
    match = await _get_chapter_for_update(db, chapter_id, user_id, is_deleted=True)
    if match is None:
        return None

    chapter, project = match
    if project.status == "回收站":
        raise ProjectInRecycleBinError("请先还原所属项目，再还原章节")
    chapter.is_deleted = False
    await _update_chapter_count(db, project)
    await db.commit()
    await db.refresh(chapter)
    return chapter


async def permanently_delete_chapter(db: AsyncSession, chapter_id: int, user_id: int):
    match = await _get_chapter_for_update(db, chapter_id, user_id, is_deleted=True)
    if match is None:
        return False

    chapter, project = match
    await db.delete(chapter)
    await _update_chapter_count(db, project)
    await db.commit()
    return True


async def get_recycled_knowledge_bases(db: AsyncSession, user_id: int):
    query = select(KnowledgeBase).options(selectinload(KnowledgeBase.documents)).where(
        KnowledgeBase.user_id == user_id,
        KnowledgeBase.is_deleted.is_(True),
    ).order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


async def _get_recycled_knowledge_base(db: AsyncSession, base_id: int, user_id: int):
    query = select(KnowledgeBase).options(selectinload(KnowledgeBase.documents)).where(
        KnowledgeBase.id == base_id,
        KnowledgeBase.user_id == user_id,
        KnowledgeBase.is_deleted.is_(True),
    ).with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def restore_knowledge_base(db: AsyncSession, base_id: int, user_id: int):
    base = await _get_recycled_knowledge_base(db, base_id, user_id)
    if base is None:
        return None
    base.is_deleted = False
    await db.commit()
    await db.refresh(base)
    return base


async def permanently_delete_knowledge_base(db: AsyncSession, base_id: int, user_id: int):
    query = select(KnowledgeBase).where(
        KnowledgeBase.id == base_id,
        KnowledgeBase.user_id == user_id,
        KnowledgeBase.is_deleted.is_(True),
    ).with_for_update()
    base = (await db.execute(query)).scalar_one_or_none()
    if base is None:
        return False
    document_ids = select(KnowledgeDocument.id).where(KnowledgeDocument.knowledge_base_id == base.id)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(document_ids)))
    await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base.id))
    await db.delete(base)
    await db.commit()
    return True
