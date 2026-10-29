"""Add volume-level outlines."""

from alembic import op
import sqlalchemy as sa


revision = "0009_outline_volumes"
down_revision = "0008_inspirations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outline_volumes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("volume_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("expected_words", sa.Integer(), nullable=False, server_default="250000"),
        sa.Column("start_chapter", sa.Integer(), nullable=True),
        sa.Column("end_chapter", sa.Integer(), nullable=True),
        sa.Column("outline", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "volume_number", name="uq_outline_volumes_project_number"),
    )
    op.create_index("ix_outline_volumes_project_id", "outline_volumes", ["project_id"])
    with op.batch_alter_table("outline_volumes") as batch_op:
        batch_op.alter_column("expected_words", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_outline_volumes_project_id", table_name="outline_volumes")
    op.drop_table("outline_volumes")
