import uuid
from datetime import timedelta, datetime

from fastapi import HTTPException
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.users import User, UserToken
from schemas.users import UserRequest, UserUpdateRequest
from utils import security
from utils.session import SESSION_TTL_SECONDS


async def get_user_by_username(db: AsyncSession, username: str):
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user_data: UserRequest):
    hashed_password = security.get_hash_password(user_data.password)
    new_user = User(username=user_data.username,password=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

async def create_token(db: AsyncSession, user_id: int):
    # Each login gets an independent session so logging in on one device does
    # not invalidate another device. Expired sessions are removed while the
    # user is logging in to keep the table bounded.
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(seconds=SESSION_TTL_SECONDS)
    await db.execute(delete(UserToken).where(UserToken.expires_at <= datetime.now()))
    db.add(UserToken(user_id=user_id, token=token, expires_at=expires_at))

    await db.commit()

    return token

async def authenticate_user(db: AsyncSession, username: str, password: str):
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not security.verify_password(password, user.password):
        return None
    return user


async def get_user_by_token(db: AsyncSession, token: str):
    query = select(UserToken).where(
        UserToken.token == token,
        UserToken.expires_at > datetime.now(),
    )
    result = await db.execute(query)
    db_token = result.scalar_one_or_none()
    if not db_token:
        return None
    query = select(User).where(User.id == db_token.user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def update_user(db: AsyncSession, username: str, user_data: UserUpdateRequest):
    query = update(User).where(User.username == username).values(**user_data.model_dump(
        exclude_unset=True,
        exclude_none=True,
    ))
    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="用户不存在")

    updated_user = await get_user_by_username(db, username)
    return updated_user

async def change_password(
    db: AsyncSession,
    user: User,
    old_password: str,
    new_password: str,
    current_token: str | None = None,
):
    if not security.verify_password(old_password, user.password):
        return False

    hashed_new_password = security.get_hash_password(new_password)
    user.password = hashed_new_password
    db.add(user)
    session_query = delete(UserToken).where(UserToken.user_id == user.id)
    if current_token:
        session_query = session_query.where(UserToken.token != current_token)
    await db.execute(session_query)
    await db.commit()
    await db.refresh(user)
    return True

async def del_token(db: AsyncSession, token: str):
    query = delete(UserToken).where(UserToken.token == token)
    await db.execute(query)

