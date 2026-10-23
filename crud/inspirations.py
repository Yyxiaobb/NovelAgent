from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.inspiration import Inspiration


async def list_inspirations(db: AsyncSession, user_id: int):
    result = await db.scalars(
        select(Inspiration)
        .where(Inspiration.user_id == user_id, Inspiration.is_deleted.is_(False))
        .order_by(Inspiration.updated_at.desc(), Inspiration.id.desc())
    )
    return result.all()


async def get_inspiration(db: AsyncSession, inspiration_id: int, user_id: int, *, include_deleted: bool = False):
    conditions = [Inspiration.id == inspiration_id, Inspiration.user_id == user_id]
    if not include_deleted:
        conditions.append(Inspiration.is_deleted.is_(False))
    return await db.scalar(select(Inspiration).where(*conditions))


async def create_inspiration(db: AsyncSession, user_id: int, *, title: str, content: str):
    item = Inspiration(user_id=user_id, title=title, content=content)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_inspiration(
    db: AsyncSession,
    inspiration: Inspiration,
    *,
    title: str,
    content: str,
    refined_content: str | None,
):
    inspiration.title = title
    inspiration.content = content
    inspiration.refined_content = refined_content
    await db.commit()
    await db.refresh(inspiration)
    return inspiration


async def move_to_recycle_bin(db: AsyncSession, inspiration: Inspiration):
    inspiration.is_deleted = True
    await db.commit()
    await db.refresh(inspiration)
    return inspiration


async def list_recycled_inspirations(db: AsyncSession, user_id: int):
    result = await db.scalars(
        select(Inspiration)
        .where(Inspiration.user_id == user_id, Inspiration.is_deleted.is_(True))
        .order_by(Inspiration.updated_at.desc(), Inspiration.id.desc())
    )
    return result.all()


async def restore_inspiration(db: AsyncSession, inspiration_id: int, user_id: int):
    item = await get_inspiration(db, inspiration_id, user_id, include_deleted=True)
    if item is None or not item.is_deleted:
        return None
    item.is_deleted = False
    await db.commit()
    await db.refresh(item)
    return item


async def permanently_delete_inspiration(db: AsyncSession, inspiration_id: int, user_id: int):
    item = await get_inspiration(db, inspiration_id, user_id, include_deleted=True)
    if item is None or not item.is_deleted:
        return False
    await db.delete(item)
    await db.commit()
    return True
