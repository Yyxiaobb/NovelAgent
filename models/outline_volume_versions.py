from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from config.db_conf import Base


class OutlineVolumeVersion(Base):
    __tablename__ = "outline_volume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    volume_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    volume_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_words: Mapped[int] = mapped_column(Integer, nullable=False)
    start_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
