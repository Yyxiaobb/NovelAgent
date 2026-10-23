"""Add persistent user inspirations with recycle-bin support."""

from alembic import op
import sqlalchemy as sa


revision = "0008_inspirations"
down_revision = "0007_knowledge_base_recycle_bin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspirations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("refined_content", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspirations_user_id", "inspirations", ["user_id"])
    op.create_index("ix_inspirations_is_deleted", "inspirations", ["is_deleted"])
    with op.batch_alter_table("inspirations") as batch_op:
        batch_op.alter_column("is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_inspirations_is_deleted", table_name="inspirations")
    op.drop_index("ix_inspirations_user_id", table_name="inspirations")
    op.drop_table("inspirations")
