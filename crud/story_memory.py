from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.projects import get_project
from models.story_memory import StoryMemory


async def list_project_memories(db: AsyncSession, project_id: int, user_id: int) -> list[StoryMemory] | None:
    if await get_project(db, project_id, user_id) is None:
        return None
    result = await db.scalars(
        select(StoryMemory)
        .where(StoryMemory.project_id == project_id)
        .order_by(StoryMemory.category, StoryMemory.title, StoryMemory.id)
    )
    return list(result.all())


async def list_active_project_memories(db: AsyncSession, project_id: int) -> list[StoryMemory]:
    result = await db.scalars(
        select(StoryMemory)
        .where(
            StoryMemory.project_id == project_id,
            StoryMemory.is_active.is_(True),
            StoryMemory.review_status == "approved",
        )
        .order_by(StoryMemory.category, StoryMemory.title)
        .limit(500)
    )
    return list(result.all())


async def create_project_memory(db: AsyncSession, project_id: int, user_id: int, payload) -> StoryMemory | None:
    if await get_project(db, project_id, user_id) is None:
        return None
    memory = StoryMemory(project_id=project_id, **payload.model_dump())
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


async def get_project_memory(
    db: AsyncSession, project_id: int, memory_id: int, user_id: int,
) -> StoryMemory | None:
    if await get_project(db, project_id, user_id) is None:
        return None
    result = await db.scalars(
        select(StoryMemory).where(StoryMemory.id == memory_id, StoryMemory.project_id == project_id)
    )
    return result.one_or_none()


async def update_project_memory(db: AsyncSession, memory: StoryMemory, payload) -> StoryMemory:
    for key, value in payload.model_dump().items():
        setattr(memory, key, value)
    await db.commit()
    await db.refresh(memory)
    return memory


async def delete_project_memory(db: AsyncSession, memory: StoryMemory) -> None:
    await db.delete(memory)
    await db.commit()


async def sync_extracted_memories(
    db: AsyncSession,
    *,
    project_id: int,
    chapter_id: int,
    chapter_number: int,
    memory: dict[str, str],
) -> None:
    """Create or refresh pending suggestions without overwriting reviewed entries."""
    categories = (
        ("character_state", "character", "人物状态"),
        ("setting_changes", "world", "设定变化"),
        ("unresolved_threads", "thread", "未解决线索"),
        ("timeline", "timeline", "时间线"),
    )
    for field, category, label in categories:
        content = (memory.get(field) or "").strip()
        result = await db.scalars(
            select(StoryMemory).where(
                StoryMemory.project_id == project_id,
                StoryMemory.source_chapter_id == chapter_id,
                StoryMemory.category == category,
                StoryMemory.origin == "chapter_extract",
            )
        )
        existing = result.one_or_none()
        if not content or content == "无":
            if existing is not None and existing.review_status == "pending":
                await db.delete(existing)
            continue
        if existing is not None:
            if existing.review_status == "pending":
                existing.content = content
            continue
        db.add(StoryMemory(
            project_id=project_id,
            source_chapter_id=chapter_id,
            category=category,
            title=f"第 {chapter_number} 章{label}",
            content=content,
            keywords=[],
            is_active=False,
            review_status="pending",
            origin="chapter_extract",
        ))
    await db.commit()


async def review_project_memory(db: AsyncSession, memory: StoryMemory, decision: str) -> StoryMemory:
    memory.review_status = decision
    memory.is_active = decision == "approved"
    await db.commit()
    await db.refresh(memory)
    return memory


async def review_project_memories(
    db: AsyncSession, memories: list[StoryMemory], decision: str,
) -> list[StoryMemory]:
    for memory in memories:
        memory.review_status = decision
        memory.is_active = decision == "approved"
    await db.commit()
    for memory in memories:
        await db.refresh(memory)
    return memories
