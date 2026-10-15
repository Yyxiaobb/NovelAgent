from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from crud import users
from config.db_conf import get_db
from models.users import User
from schemas.users import UserRequest, UserInfoResponse, UserAuthResponse, UserUpdateRequest, UserChangePasswordRequest
from utils.response import success_response
from utils.auth import get_current_user, get_current_user_token

router = APIRouter(prefix="/api/user", tags=["users"])

@router.post("/register")
async def register(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    existing_user = await users.get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    user = await users.create_user(db, user_data)
    token = await users.create_token(db, user.id)
    response = UserAuthResponse(token=token, user_info=UserInfoResponse.model_validate(user))
    return success_response(message="注册成功", data=response)

@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await users.authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = await users.create_token(db, user.id)
    response = UserAuthResponse(token=token, user_info=UserInfoResponse.model_validate(user))
    return success_response(message="登录成功", data=response)

@router.get("/info")
async def get_user_info(user: User = Depends(get_current_user)):
    return success_response(message="获取用户信息出成功", data=UserInfoResponse.model_validate(user))

@router.put("/update")
async def update_user_info(user_data: UserUpdateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    updated_user = await users.update_user(db, user.username, user_data)
    return success_response(message="资料更新成功", data=UserInfoResponse.model_validate(updated_user))


@router.put("/password")
async def update_password(password_data: UserChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    updated_pwd = await users.change_password(db, user, password_data.old_password, password_data.new_password)
    if not updated_pwd:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    return success_response(message="修改成功")

@router.post("/logout")
async def logout(token: str = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    await users.del_token(db, token)
    await db.commit()
    return success_response(message="退出登录")
