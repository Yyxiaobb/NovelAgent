"""Add soft deletion for volume outlines."""

from alembic import op
import sqlalchemy as sa


revision = "0010_outline_volume_recycle_bin"
down_revision = "0009_outline_volumes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outline_volumes",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("outline_volumes") as batch_op:
        batch_op.alter_column("is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_column("outline_volumes", "is_deleted")
