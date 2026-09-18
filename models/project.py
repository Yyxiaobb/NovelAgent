from datetime import datetime
from typing import Optional
from sqlalchemy import Index, Integer, String, Enum, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .users import User

class Base(DeclarativeBase):
    pass

class Project(Base):
    __tablename__ = 'project'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="项目ID")
    projectname: Mapped[str] = mapped_column(String(50), nullable=False, comment="项目名称")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(User.id), nullable=False, comment="用户ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<Project={self.id}, user_id={self.user_id}, project_name={self.projectname}, created_at={self.created_at}, updated_at={self.updated_at}>"

