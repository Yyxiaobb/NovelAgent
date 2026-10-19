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
        .where(StoryMemory.project_id == project_id, StoryMemory.is_active.is_(True))
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
