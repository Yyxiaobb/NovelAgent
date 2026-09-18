from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

class UserRequest(BaseModel):
    username: str
    password: str

class UserInfoBase(BaseModel):
    """
    用户信息基础模型
    """
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")
    gender: Optional[Literal["male", "female", "unknown"]] = Field(None, description="性别")
    bio: Optional[str] = Field(None, max_length=500, description="个人简介")

class UserInfoResponse(UserInfoBase):
    id: int
    username: str

    model_config = ConfigDict(
        from_attributes=True
    )

class UserAuthResponse(BaseModel):
    token: str
    user_info: UserInfoResponse = Field(..., alias="userInfo")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

class UserUpdateRequest(UserInfoBase):
    phone: Optional[str] = Field(None, pattern=r"^1[3456789]\d{9}$", description="手机号")

class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., alias="oldPassword", description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=128, alias="newPassword", description="新密码")

    model_config = ConfigDict(
        populate_by_name=True
    )


