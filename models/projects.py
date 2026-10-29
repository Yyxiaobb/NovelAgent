from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, Integer, String, Enum, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.db_conf import Base


PROJECT_STATE_TEMPLATE = """# 当前状态

> 根据已保存正文持续整理；仅记录正文或作品设定中明确的信息。可手动修订。

## 世界观
待从作品设定和正文中整理。

## 规则与体系
待从作品设定和正文中整理。

## 主角状态
待从正文中整理。

## 人物关系与人脉
待从正文中整理。

## 时间线与当前位置
待从正文中整理。

## 当前主线与未解事项
待从正文中整理。

## 最近进展
尚无已保存正文。
"""


class Project(Base):
    __tablename__ = 'project'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="项目ID")
    projectname: Mapped[str] = mapped_column(String(50), nullable=True, index=True, comment="项目名称")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="用户ID")
    introduction: Mapped[Optional[str]] = mapped_column(String(1000), comment="小说简介")
    project_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, comment="作品类型")
    cover_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="作品封面地址")
    outline: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="作品大纲")
    current_state_markdown: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=PROJECT_STATE_TEMPLATE, comment="作品当前状态 Markdown"
    )
    expected_words: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="期望作品字数")
    total_words: Mapped[int] = mapped_column(Integer, default=0, comment="总字数")
    chapter_count: Mapped[int] = mapped_column(Integer, default=0, comment="章节数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")
    status: Mapped[Optional[str]] = mapped_column(Enum("连载中", "完结", "断更", "回收站"), default="连载中", comment="项目状态")
    previous_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="移入回收站前的项目状态")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Chapter.chapter_number"
    )

    def __repr__(self):
        return f"<Project={self.id}, user_id={self.user_id}, project_name={self.projectname}, created_at={self.created_at}, updated_at={self.updated_at}>"

class Chapter(Base):
    __tablename__ = 'chapters'
    __table_args__ = (
        UniqueConstraint('project_id', 'chapter_number', name='uq_chapters_project_number'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="章节ID")
    chapter_number: Mapped[int]
    chaptername: Mapped[str] = mapped_column(String(50), nullable=True, comment="章节名")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="章节内容")
    plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="章节规划")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="章节摘要")
    memory: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="章节记忆")
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("project.id"), nullable=False, comment="项目ID")
    volume_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("outline_volumes.id", ondelete="SET NULL"), nullable=True, index=True, comment="所属卷纲ID"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否已移入回收站")
    project: Mapped["Project"] = relationship(back_populates="chapters")

    @property
    def word_count(self) -> int:
        """当前章节正文的字符数，供 API 和项目统计统一使用。"""
        return len(self.content or "")
