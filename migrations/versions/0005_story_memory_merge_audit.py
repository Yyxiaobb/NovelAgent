"""Add memory merge tracking and immutable audit events."""

from alembic import op
import sqlalchemy as sa


revision = "0005_story_memory_merge_audit"
down_revision = "0004_story_memory_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_memories", sa.Column("merged_into_id", sa.Integer(), nullable=True))
    op.create_index("ix_story_memories_merged_into_id", "story_memories", ["merged_into_id"])
    with op.batch_alter_table("story_memories") as batch_op:
        batch_op.create_foreign_key(
            "fk_story_memories_merged_into_id", "story_memories",
            ["merged_into_id"], ["id"], ondelete="SET NULL",
        )
    op.create_table(
        "story_memory_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("memory_id", sa.Integer(), nullable=True),
        sa.Column("related_memory_ids", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["story_memories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_story_memory_events_project_id", "story_memory_events", ["project_id"])
    op.create_index("ix_story_memory_events_actor_user_id", "story_memory_events", ["actor_user_id"])
    op.create_index("ix_story_memory_events_event_type", "story_memory_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_story_memory_events_event_type", table_name="story_memory_events")
    op.drop_index("ix_story_memory_events_actor_user_id", table_name="story_memory_events")
    op.drop_index("ix_story_memory_events_project_id", table_name="story_memory_events")
    op.drop_table("story_memory_events")
    with op.batch_alter_table("story_memories") as batch_op:
        batch_op.drop_constraint("fk_story_memories_merged_into_id", type_="foreignkey")
    op.drop_index("ix_story_memories_merged_into_id", table_name="story_memories")
    op.drop_column("story_memories", "merged_into_id")
