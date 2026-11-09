from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select

from schemas.projects import ChapterRequest, OutlineRequest, ProjectRequest
from models.projects import Chapter, Project
from models.outline_volume import OutlineVolume
from models.users import User
from crud import versions as chapter_versions
from crud import outline_versions
from crud import outline_volume_versions


class ChapterNumberConflictError(Exception):
    """Raised when a project already owns the requested chapter number."""


class ChapterVolumeConflictError(Exception):
    """Raised when a chapter is assigned to a volume from another project or a deleted volume."""

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
    project.total_words = sum(chapter.word_count for chapter in chapters)

async def create_new_pro(db: AsyncSession, pro_data: ProjectRequest, user_id: int):
    # Serialize project creation per user so concurrent requests cannot choose
    # the same reusable display number. Recycled projects remain in this query
    # and therefore keep their number reserved.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    if not pro_data.projectname:
        existing_names = await db.scalars(select(Project.projectname).where(Project.user_id == user_id))
        occupied_numbers = {
            int(name)
            for name in existing_names
            if isinstance(name, str) and name.isdecimal() and int(name) > 0
        }
        project_number = 1
        while project_number in occupied_numbers:
            project_number += 1
        project_name = f"{project_number:02d}"
    else:
        project_name = pro_data.projectname

    new_pro = Project(
        projectname=project_name,
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


async def update_project_state(db: AsyncSession, project_id: int, user_id: int, markdown: str):
    project = await get_project(db, project_id, user_id)
    if project is None:
        return None
    project.current_state_markdown = markdown
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
    if "expected_words" in payload.model_fields_set:
        project.expected_words = payload.expected_words
    await db.commit()
    await db.refresh(project)
    return project


async def get_outline_volumes(db: AsyncSession, project_id: int):
    result = await db.scalars(
        select(OutlineVolume).where(
            OutlineVolume.project_id == project_id, OutlineVolume.is_deleted.is_(False)
        ).order_by(OutlineVolume.volume_number)
    )
    return list(result.all())


def resolve_outline_volume(volumes, volume_id: int | None = None, *, active_only: bool = True):
    """Resolve a chapter volume or the current unfinished volume.

    Planning uses ``active_only`` so a completed volume advances the story;
    content generation can opt into a completed chapter's historical volume.
    """
    if volume_id is not None:
        assigned = next((item for item in volumes if item.id == volume_id), None)
        if assigned is not None and (not active_only or not assigned.is_completed):
            return assigned
    return next((item for item in volumes if not item.is_completed), None)


async def create_outline_volume(db: AsyncSession, project_id: int, payload):
    current = await db.scalars(select(OutlineVolume.volume_number).where(OutlineVolume.project_id == project_id))
    volume_number = max(current.all(), default=0) + 1
    volume = OutlineVolume(
        project_id=project_id,
        volume_number=volume_number,
        name=payload.name,
        start_chapter=payload.start_chapter,
        end_chapter=payload.end_chapter,
        outline=payload.outline,
    )
    db.add(volume)
    await db.flush()
    if payload.volume_number is not None:
        await _reorder_outline_volumes(db, project_id, volume.id, payload.volume_number)
    await db.commit()
    await db.refresh(volume)
    return volume


async def update_outline_volume(db: AsyncSession, project_id: int, volume_id: int, user_id: int, payload):
    volume = await db.scalar(
        select(OutlineVolume).where(
            OutlineVolume.project_id == project_id, OutlineVolume.id == volume_id, OutlineVolume.is_deleted.is_(False)
        )
    )
    if volume is None:
        return None
    await outline_volume_versions.add_snapshot(db, volume, user_id)
    if payload.volume_number is not None and payload.volume_number != volume.volume_number:
        await _reorder_outline_volumes(db, project_id, volume.id, payload.volume_number, user_id=user_id)
    for field in ("name", "outline"):
        if field in payload.model_fields_set:
            setattr(volume, field, getattr(payload, field))
    for field in ("start_chapter", "end_chapter"):
        value = getattr(payload, field)
        if field in payload.model_fields_set and value is not None:
            setattr(volume, field, value)
    await db.commit()
    await db.refresh(volume)
    return volume


async def _reorder_outline_volumes(
    db: AsyncSession,
    project_id: int,
    volume_id: int,
    requested_number: int,
    *,
    user_id: int | None = None,
) -> None:
    """Move one active volume to a requested position and compact active numbers."""
    active = list((await db.scalars(select(OutlineVolume).where(
        OutlineVolume.project_id == project_id,
        OutlineVolume.is_deleted.is_(False),
    ).order_by(OutlineVolume.volume_number, OutlineVolume.id))).all())
    target = next((item for item in active if item.id == volume_id), None)
    if target is None:
        return
    old_order = [item.id for item in active]
    active.remove(target)
    active.insert(max(0, min(requested_number - 1, len(active))), target)
    if [item.id for item in active] == old_order:
        return
    if user_id is not None:
        for item in active:
            if item.id != volume_id and item.volume_number != old_order.index(item.id) + 1:
                await outline_volume_versions.add_snapshot(db, item, user_id, source="reorder")
    # Deleted rows retain their numbers, so choose the next available positive
    # sequence while using temporary negatives to avoid unique-key collisions.
    reserved = set((await db.scalars(select(OutlineVolume.volume_number).where(
        OutlineVolume.project_id == project_id,
        OutlineVolume.is_deleted.is_(True),
    ))).all())
    for index, item in enumerate(active, start=1):
        item.volume_number = -index
    await db.flush()
    next_number = 1
    for item in active:
        while next_number in reserved:
            next_number += 1
        item.volume_number = next_number
        next_number += 1


async def delete_outline_volume(db: AsyncSession, project_id: int, volume_id: int):
    volume = await db.scalar(
        select(OutlineVolume).where(
            OutlineVolume.project_id == project_id, OutlineVolume.id == volume_id, OutlineVolume.is_deleted.is_(False)
        )
    )
    if volume is None:
        return False
    project = await db.get(Project, project_id)
    if project is not None:
        await outline_volume_versions.add_snapshot(db, volume, project.user_id)
    volume.is_deleted = True
    await db.commit()
    return True


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
    resolved_volume_id = payload.volume_id
    if resolved_volume_id is not None:
        volume = await db.scalar(select(OutlineVolume).where(
            OutlineVolume.id == resolved_volume_id,
            OutlineVolume.project_id == project.id,
            OutlineVolume.is_deleted.is_(False),
        ))
        if volume is None:
            raise ChapterVolumeConflictError("所属卷纲不存在、已删除或不属于当前作品")
    else:
        volume = await db.scalar(select(OutlineVolume).where(
            OutlineVolume.project_id == project.id,
            OutlineVolume.is_deleted.is_(False),
            OutlineVolume.is_completed.is_(False),
        ).order_by(OutlineVolume.volume_number).limit(1))
        if volume is not None:
            resolved_volume_id = volume.id
    chapter = Chapter(
        project_id=project.id,
        chapter_number=payload.chapter_number,
        chaptername=payload.chaptername,
        content=payload.content,
        plan=payload.plan.model_dump() if payload.plan is not None else None,
        summary=payload.summary,
        memory=payload.memory.model_dump() if payload.memory is not None else None,
        volume_id=resolved_volume_id,
    )
    db.add(chapter)
    if payload.volume_complete and resolved_volume_id is not None:
        volume = await db.get(OutlineVolume, resolved_volume_id)
        if volume is not None:
            volume.is_completed = True
            volume.completion_note = payload.volume_completion_note
            volume.completed_at = datetime.now()
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
    if "volume_id" in payload.model_fields_set and payload.volume_id is not None:
        volume = await db.scalar(select(OutlineVolume).where(
            OutlineVolume.id == payload.volume_id,
            OutlineVolume.project_id == project.id,
            OutlineVolume.is_deleted.is_(False),
        ))
        if volume is None:
            raise ChapterVolumeConflictError("所属卷纲不存在、已删除或不属于当前作品")
    await chapter_versions.add_snapshot(
        db,
        chapter,
        user_id,
        source="plan_edit" if "plan" in payload.model_fields_set else "manual",
    )
    chapter.chapter_number = payload.chapter_number
    chapter.chaptername = payload.chaptername
    chapter.content = payload.content
    if "plan" in payload.model_fields_set:
        chapter.plan = payload.plan.model_dump() if payload.plan is not None else None
    if "summary" in payload.model_fields_set:
        chapter.summary = payload.summary
    if "memory" in payload.model_fields_set:
        chapter.memory = payload.memory.model_dump() if payload.memory is not None else None
    if "volume_id" in payload.model_fields_set:
        chapter.volume_id = payload.volume_id
    elif "plan" in payload.model_fields_set:
        active_volume = await db.scalar(select(OutlineVolume).where(
            OutlineVolume.project_id == project.id,
            OutlineVolume.is_deleted.is_(False),
            OutlineVolume.is_completed.is_(False),
        ).order_by(OutlineVolume.volume_number).limit(1))
        if active_volume is not None:
            chapter.volume_id = active_volume.id
    if payload.volume_complete and chapter.volume_id is not None:
        volume = await db.scalar(select(OutlineVolume).where(
            OutlineVolume.id == chapter.volume_id,
            OutlineVolume.project_id == project.id,
            OutlineVolume.is_deleted.is_(False),
        ))
        if volume is not None:
            volume.is_completed = True
            volume.completion_note = payload.volume_completion_note
            volume.completed_at = datetime.now()
    await recalculate_project_stats(db, project, lock=True)
    await db.commit()
    await db.refresh(chapter)
    return chapter
