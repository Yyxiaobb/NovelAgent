"""Track model-judged completion of each volume outline."""

from alembic import op
import sqlalchemy as sa


revision = "0013_outline_volume_progress"
down_revision = "0012_chapter_volume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outline_volumes") as batch_op:
        batch_op.add_column(sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("completion_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch_op.alter_column("is_completed", server_default=None)

def downgrade() -> None:
    with op.batch_alter_table("outline_volumes") as batch_op:
        batch_op.drop_column("completed_at")
        batch_op.drop_column("completion_note")
        batch_op.drop_column("is_completed")
