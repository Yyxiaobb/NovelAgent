"""Add the project-level Markdown current state document."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0014_project_current_state"
down_revision = "0013_outline_volume_progress"
branch_labels = None
depends_on = None


_INITIAL_STATE = """# 当前状态

> 根据已保存正文持续整理；仅记录正文或作品设定中明确的信息。可手动修订。

## 世界观
待从作品设定和正文中整理。

## 规则与体系
待从作品设定和正文中整理。

## 主角状态
待从正文中整理。

## 人物关系与人脉
待从正文中整理。

## 时间线与当前位置
待从正文中整理。

## 当前主线与未解事项
待从正文中整理。

## 最近进展
尚无已保存正文。
"""


def upgrade() -> None:
    bind = op.get_bind()
    project_columns = {item["name"] for item in inspect(bind).get_columns("project")}
    if "current_state_markdown" not in project_columns:
        op.add_column(
            "project",
            sa.Column("current_state_markdown", sa.Text(), nullable=True),
        )
    bind.execute(
        sa.text(
            "UPDATE project SET current_state_markdown = :initial_state "
            "WHERE current_state_markdown IS NULL"
        ),
        {"initial_state": _INITIAL_STATE},
    )


def downgrade() -> None:
    project_columns = {item["name"] for item in inspect(op.get_bind()).get_columns("project")}
    if "current_state_markdown" in project_columns:
        op.drop_column("project", "current_state_markdown")
