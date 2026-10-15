from datetime import datetime
from typing import Optional
from sqlalchemy import Index, Integer, String, Enum, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.db_conf import Base
from .users import User


class Project(Base):
    __tablename__ = 'project'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="项目ID")
    projectname: Mapped[str] = mapped_column(String(50), nullable=True, index=True, comment="项目名称")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="用户ID")
    introduction: Mapped[Optional[str]] = mapped_column(String(1000), comment="小说简介")
    total_words: Mapped[int] = mapped_column(Integer, default=0, comment="总字数")
    chapter_count: Mapped[int] = mapped_column(Integer, default=0, comment="章节数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")
    status: Mapped[Optional[str]] = mapped_column(Enum("连载中", "完结", "断更", "回收站"), default="连载中", comment="项目状态")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Chapter.chapter_number"
    )

    def __repr__(self):
        return f"<Project={self.id}, user_id={self.user_id}, project_name={self.projectname}, created_at={self.created_at}, updated_at={self.updated_at}>"

class Chapter(Base):
    __tablename__ = 'chapters'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="章节ID")
    chapter_number: Mapped[int]
    chaptername: Mapped[str] = mapped_column(String(50), nullable=True, comment="章节名")
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("project.id"), nullable=False, comment="项目ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    project: Mapped["Project"] = relationship(back_populates="chapters")
