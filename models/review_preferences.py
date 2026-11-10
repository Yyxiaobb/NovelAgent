from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from config.db_conf import Base


class ReviewPreferences(Base):
    __tablename__ = "review_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_review_preferences_scope"),
        Index(
            "uq_review_preferences_account_scope",
            "user_id",
            unique=True,
            sqlite_where=text("project_id IS NULL"),
            postgresql_where=text("project_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=True, index=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    max_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accept_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manual_approval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
