"""Add version snapshots for volume outlines."""

from alembic import op
import sqlalchemy as sa


revision = "0011_outline_volume_versions"
down_revision = "0010_outline_volume_recycle_bin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outline_volume_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("volume_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("volume_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("expected_words", sa.Integer(), nullable=False),
        sa.Column("start_chapter", sa.Integer(), nullable=True),
        sa.Column("end_chapter", sa.Integer(), nullable=True),
        sa.Column("outline", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outline_volume_versions_project_id", "outline_volume_versions", ["project_id"])
    op.create_index("ix_outline_volume_versions_user_id", "outline_volume_versions", ["user_id"])
    op.create_index("ix_outline_volume_versions_volume_id", "outline_volume_versions", ["volume_id"])


def downgrade() -> None:
    op.drop_index("ix_outline_volume_versions_volume_id", table_name="outline_volume_versions")
    op.drop_index("ix_outline_volume_versions_user_id", table_name="outline_volume_versions")
    op.drop_index("ix_outline_volume_versions_project_id", table_name="outline_volume_versions")
    op.drop_table("outline_volume_versions")
