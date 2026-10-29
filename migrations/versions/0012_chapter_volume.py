"""Associate chapters with outline volumes."""

from alembic import op
import sqlalchemy as sa


revision = "0012_chapter_volume"
down_revision = "0011_outline_volume_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.add_column(sa.Column("volume_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_chapters_volume_id", ["volume_id"])
        batch_op.create_foreign_key(
            "fk_chapters_volume_id_outline_volumes", "outline_volumes", ["volume_id"], ["id"], ondelete="SET NULL"
        )
    # Populate existing chapters when a volume has an explicit chapter range.
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        bind.execute(sa.text(
            "UPDATE chapters c JOIN outline_volumes v ON v.project_id = c.project_id "
            "AND v.is_deleted = 0 AND v.start_chapter IS NOT NULL "
            "AND c.chapter_number >= v.start_chapter "
            "AND (v.end_chapter IS NULL OR c.chapter_number <= v.end_chapter) "
            "SET c.volume_id = v.id WHERE c.volume_id IS NULL"
        ))


def downgrade() -> None:
    with op.batch_alter_table("chapters") as batch_op:
        batch_op.drop_constraint("fk_chapters_volume_id_outline_volumes", type_="foreignkey")
        batch_op.drop_index("ix_chapters_volume_id")
        batch_op.drop_column("volume_id")
