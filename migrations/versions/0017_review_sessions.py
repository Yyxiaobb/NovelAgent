"""Persist human-in-the-loop editorial review sessions."""

from alembic import op
import sqlalchemy as sa


revision = "0017_review_sessions"
down_revision = "0016_unique_account_review_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("generation_job_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("accept_score", sa.Integer(), nullable=False),
        sa.Column("initial_content", sa.Text(), nullable=False),
        sa.Column("draft_content", sa.Text(), nullable=False),
        sa.Column("generation_payload", sa.JSON(), nullable=False),
        sa.Column("review_history", sa.JSON(), nullable=False),
        sa.Column("latest_review", sa.JSON(), nullable=True),
        sa.Column("revision_decisions", sa.JSON(), nullable=False),
        sa.Column("manual_decisions", sa.JSON(), nullable=False),
        sa.Column("last_continue_request_id", sa.String(length=64), nullable=True),
        sa.Column("last_continue_response", sa.JSON(), nullable=True),
        sa.Column("stop_reason", sa.String(length=40), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_sessions_user_id", "review_sessions", ["user_id"])
    op.create_index("ix_review_sessions_project_id", "review_sessions", ["project_id"])
    op.create_index("ix_review_sessions_chapter_id", "review_sessions", ["chapter_id"])
    op.create_index("ix_review_sessions_generation_job_id", "review_sessions", ["generation_job_id"])
    op.create_index("ix_review_sessions_status", "review_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_review_sessions_status", table_name="review_sessions")
    op.drop_index("ix_review_sessions_generation_job_id", table_name="review_sessions")
    op.drop_index("ix_review_sessions_chapter_id", table_name="review_sessions")
    op.drop_index("ix_review_sessions_project_id", table_name="review_sessions")
    op.drop_index("ix_review_sessions_user_id", table_name="review_sessions")
    op.drop_table("review_sessions")
