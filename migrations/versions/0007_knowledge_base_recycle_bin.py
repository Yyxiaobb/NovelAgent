"""Add soft-delete state for knowledge bases."""

from alembic import op
import sqlalchemy as sa


revision = "0007_knowledge_base_recycle_bin"
down_revision = "0006_user_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_knowledge_bases_is_deleted", "knowledge_bases", ["is_deleted"])
    with op.batch_alter_table("knowledge_bases") as batch_op:
        batch_op.alter_column("is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_knowledge_bases_is_deleted", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "is_deleted")
