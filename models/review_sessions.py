from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from config.db_conf import Base


class ReviewSession(Base):
    """Persisted human-in-the-loop editorial review for a generated draft."""

    __tablename__ = "review_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="awaiting_review", index=True)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    accept_score: Mapped[int] = mapped_column(Integer, nullable=False, default=85)
    initial_content: Mapped[str] = mapped_column(Text, nullable=False)
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    generation_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    latest_review: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    revision_decisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    manual_decisions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_continue_request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_continue_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stop_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
