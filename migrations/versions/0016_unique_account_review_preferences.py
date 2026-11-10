"""Ensure each account has at most one default review preference record."""

from alembic import op
import sqlalchemy as sa


revision = "0016_unique_account_review_preferences"
down_revision = "0015_review_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_review_preferences_account_scope",
        "review_preferences",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
        postgresql_where=sa.text("project_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_review_preferences_account_scope", table_name="review_preferences")
