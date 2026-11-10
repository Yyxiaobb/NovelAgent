"""Persist account and project review preferences."""

from alembic import op
import sqlalchemy as sa


revision = "0015_review_preferences"
down_revision = "0014_project_current_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("max_rounds", sa.Integer(), nullable=True),
        sa.Column("accept_score", sa.Integer(), nullable=True),
        sa.Column("manual_approval", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project_id", name="uq_review_preferences_scope"),
    )
    op.create_index("ix_review_preferences_user_id", "review_preferences", ["user_id"])
    op.create_index("ix_review_preferences_project_id", "review_preferences", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_review_preferences_project_id", table_name="review_preferences")
    op.drop_index("ix_review_preferences_user_id", table_name="review_preferences")
    op.drop_table("review_preferences")
