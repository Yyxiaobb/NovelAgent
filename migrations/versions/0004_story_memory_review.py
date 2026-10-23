"""Add review workflow and provenance for extracted story memories."""

from alembic import op
import sqlalchemy as sa


revision = "0004_story_memory_review"
down_revision = "0003_project_story_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "story_memories",
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="approved"),
    )
    op.add_column(
        "story_memories",
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.create_index("ix_story_memories_review_status", "story_memories", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_story_memories_review_status", table_name="story_memories")
    op.drop_column("story_memories", "origin")
    op.drop_column("story_memories", "review_status")
