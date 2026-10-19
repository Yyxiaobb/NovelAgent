"""Baseline schema and compatibility upgrade for existing installations."""

from alembic import context, op
from sqlalchemy import inspect, text

from config.db_conf import Base

# Import models before using metadata.create_all.
from models import generation, outline_versions, projects, users, versions  # noqa: F401


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _add_missing_mysql_columns(bind) -> None:
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "project" not in tables or "chapters" not in tables:
        return

    project_columns = {item["name"]: item for item in inspector.get_columns("project")}
    status = project_columns.get("status")
    if status is not None and "回收站" not in getattr(status["type"], "enums", ()):
        bind.execute(text(
            "ALTER TABLE project MODIFY COLUMN status "
            "ENUM('连载中', '完结', '断更', '回收站') NULL COMMENT '项目状态'"
        ))

    additions = {
        "previous_status": "VARCHAR(20) NULL COMMENT '移入回收站前的项目状态'",
        "project_type": "VARCHAR(30) NULL COMMENT '作品类型'",
        "cover_url": "VARCHAR(500) NULL COMMENT '作品封面地址'",
        "outline": "LONGTEXT NULL COMMENT '作品大纲'",
        "expected_words": "INT NULL COMMENT '期望作品字数'",
    }
    for name, definition in additions.items():
        if name not in project_columns:
            bind.execute(text(f"ALTER TABLE project ADD COLUMN {name} {definition}"))

    chapter_columns = {item["name"] for item in inspector.get_columns("chapters")}
    chapter_additions = {
        "is_deleted": "BOOLEAN NOT NULL DEFAULT 0 COMMENT '是否已移入回收站'",
        "content": "LONGTEXT NULL COMMENT '章节内容'",
        "plan": "JSON NULL COMMENT '章节规划'",
        "summary": "LONGTEXT NULL COMMENT '章节摘要'",
        "memory": "JSON NULL COMMENT '章节记忆'",
    }
    for name, definition in chapter_additions.items():
        if name not in chapter_columns:
            bind.execute(text(f"ALTER TABLE chapters ADD COLUMN {name} {definition}"))


def upgrade() -> None:
    bind = op.get_bind()

    # Create missing tables while preserving existing user data. This is the
    # baseline for databases created before Alembic was introduced.
    # Chapter numbering is introduced by 0002 so that old databases can be
    # checked for duplicates before the constraint is created.
    chapter_table = Base.metadata.tables.get("chapters")
    numbering_constraint = next(
        (item for item in chapter_table.constraints
         if item.name == "uq_chapters_project_number"),
        None,
    ) if chapter_table is not None else None
    if numbering_constraint is not None:
        chapter_table.constraints.remove(numbering_constraint)
    try:
        # Later versioned tables are intentionally excluded from the baseline;
        # their dedicated revisions create them in order.
        later_tables = {"story_memories", "story_memory_events"}
        baseline_tables = [table for table in Base.metadata.sorted_tables if table.name not in later_tables]
        Base.metadata.create_all(bind=bind, tables=baseline_tables)
    finally:
        if numbering_constraint is not None:
            chapter_table.append_constraint(numbering_constraint)

    if bind.dialect.name == "mysql" and not context.is_offline_mode():
        _add_missing_mysql_columns(bind)


def downgrade() -> None:
    # Dropping the baseline tables could destroy user content, so a safe
    # rollback will be introduced only with a dedicated data migration.
    raise RuntimeError("The baseline migration cannot be downgraded safely")
