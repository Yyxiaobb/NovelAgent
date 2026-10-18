from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.db_conf import get_db
from crud import users

security = HTTPBearer(auto_error=False)
SESSION_COOKIE_NAME = "novel-agent-session"


async def get_current_user_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    # Bearer tokens remain supported for API clients. Browser sessions use the
    # HttpOnly cookie so JavaScript does not need to read the credential.
    token = credentials.credentials if credentials else request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token

async def get_current_user(token: str = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user = await users.get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌或已经过期的令牌")
    return user
