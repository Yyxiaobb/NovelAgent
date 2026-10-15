from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.db_conf import get_db
from crud import users

security = HTTPBearer()
async def get_current_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return credentials.credentials

async def get_current_user(token: str = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user = await users.get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌或已经过期的令牌")
    return user
