"""Add curated long-term story memories."""

from alembic import op
import sqlalchemy as sa


revision = "0003_project_story_memories"
down_revision = "0002_consistent_project_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("source_chapter_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_story_memories_project_id", "story_memories", ["project_id"])
    op.create_index("ix_story_memories_category", "story_memories", ["category"])
    op.create_index("ix_story_memories_is_active", "story_memories", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_story_memories_is_active", table_name="story_memories")
    op.drop_index("ix_story_memories_category", table_name="story_memories")
    op.drop_index("ix_story_memories_project_id", table_name="story_memories")
    op.drop_table("story_memories")
