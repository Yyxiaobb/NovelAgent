"""Enforce chapter numbering and rebuild denormalized project statistics."""

from alembic import context, op
from sqlalchemy import inspect, text


revision = "0002_consistent_project_stats"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _has_chapter_number_constraint(bind) -> bool:
    inspector = inspect(bind)
    expected = {"project_id", "chapter_number"}
    for item in inspector.get_unique_constraints("chapters"):
        if set(item.get("column_names") or ()) == expected:
            return True
    for item in inspector.get_indexes("chapters"):
        if item.get("unique") and set(item.get("column_names") or ()) == expected:
            return True
    return False


def _reject_duplicate_chapter_numbers(bind) -> None:
    duplicates = bind.execute(text(
        "SELECT project_id, chapter_number, COUNT(*) AS duplicate_count "
        "FROM chapters GROUP BY project_id, chapter_number "
        "HAVING COUNT(*) > 1"
    )).fetchall()
    if duplicates:
        sample = ", ".join(f"project={row[0]}, chapter={row[1]}" for row in duplicates[:5])
        raise RuntimeError(
            "Cannot add the chapter number constraint because duplicate chapter "
            f"numbers exist ({sample}). Resolve them before rerunning Alembic."
        )


def _rebuild_project_stats(bind) -> None:
    length_function = "CHAR_LENGTH" if bind.dialect.name == "mysql" else "LENGTH"
    rows = bind.execute(text(
        "SELECT p.id, COUNT(c.id), "
        f"COALESCE(SUM({length_function}(COALESCE(c.content, ''))), 0) "
        "FROM project p LEFT JOIN chapters c "
        "ON c.project_id = p.id AND COALESCE(c.is_deleted, 0) = 0 "
        "GROUP BY p.id"
    )).fetchall()
    for project_id, chapter_count, total_words in rows:
        bind.execute(
            text("UPDATE project SET chapter_count = :chapter_count, total_words = :total_words WHERE id = :project_id"),
            {"project_id": project_id, "chapter_count": chapter_count, "total_words": total_words},
        )


def upgrade() -> None:
    bind = op.get_bind()

    if context.is_offline_mode():
        # Offline SQL cannot inspect existing duplicate data. The generated
        # script still includes the DDL for a clean database.
        op.create_unique_constraint(
            "uq_chapters_project_number", "chapters", ["project_id", "chapter_number"]
        )
        return

    _reject_duplicate_chapter_numbers(bind)
    if not _has_chapter_number_constraint(bind):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("chapters") as batch_op:
                batch_op.create_unique_constraint(
                    "uq_chapters_project_number", ["project_id", "chapter_number"]
                )
        else:
            op.create_unique_constraint(
                "uq_chapters_project_number", "chapters", ["project_id", "chapter_number"]
            )
    _rebuild_project_stats(bind)


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_constraint("uq_chapters_project_number", "chapters", type_="unique")
        return

    bind = op.get_bind()
    if not _has_chapter_number_constraint(bind):
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.drop_constraint("uq_chapters_project_number", type_="unique")
    else:
        op.drop_constraint("uq_chapters_project_number", "chapters", type_="unique")
