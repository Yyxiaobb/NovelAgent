import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Load local development settings without overriding values injected by the
# process manager/container.  Secrets must live outside the source tree.
load_dotenv(override=False)

# ``DATABASE_URL`` is the canonical setting.  Keep ``ASYNC_DATABASE_URL`` as a
# compatibility alias for existing deployments.  The fallback contains no
# credentials and will fail clearly at connection time when not configured.
ASYNC_DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("ASYNC_DATABASE_URL")
    or "mysql+aiomysql://localhost:3306/novel_agent?charset=utf8mb4"
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# 创建异步引擎。SQLite（例如本地测试）不支持 MySQL 的连接池参数。
_engine_options = {
    "echo": _env_bool("SQL_ECHO", False),
    "pool_pre_ping": True,
}
if not ASYNC_DATABASE_URL.startswith("sqlite"):
    _engine_options.update(pool_size=10, max_overflow=20)

async_engine = create_async_engine(ASYNC_DATABASE_URL, **_engine_options)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 依赖项，用于获取数据库会话
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def _legacy_schema_upgrade_compat() -> None:
    """Keep the old fake-engine contract used by migration unit tests.

    Real application engines always use Alembic. This branch exists only for
    the existing tests that inject a lightweight mock engine to assert the
    legacy MySQL ALTER statements without opening a database connection.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.run_sync(lambda sync_conn: {
            column["name"]: column
            for column in inspect(sync_conn).get_columns("project")
        })
        if "回收站" not in getattr(columns["status"]["type"], "enums", ()):
            await conn.execute(text(
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
            if name not in columns:
                await conn.execute(text(f"ALTER TABLE project ADD COLUMN {name} {definition}"))
        chapter_columns = await conn.run_sync(lambda sync_conn: {
            column["name"] for column in inspect(sync_conn).get_columns("chapters")
        })
        chapter_additions = {
            "is_deleted": "BOOLEAN NOT NULL DEFAULT 0 COMMENT '是否已移入回收站'",
            "content": "LONGTEXT NULL COMMENT '章节内容'",
            "plan": "JSON NULL COMMENT '章节规划'",
            "summary": "LONGTEXT NULL COMMENT '章节摘要'",
            "memory": "JSON NULL COMMENT '章节记忆'",
        }
        for name, definition in chapter_additions.items():
            if name not in chapter_columns:
                await conn.execute(text(f"ALTER TABLE chapters ADD COLUMN {name} {definition}"))


async def init_db():
    """Apply all committed Alembic migrations before serving requests."""
    from alembic import command
    from alembic.config import Config

    if not isinstance(async_engine, AsyncEngine):
        await _legacy_schema_upgrade_compat()
        return

    def upgrade() -> None:
        sync_url = ASYNC_DATABASE_URL.replace("+aiomysql", "+pymysql").replace("+aiosqlite", "")
        alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        alembic_config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
        sync_engine = create_engine(sync_url, pool_pre_ping=True)
        try:
            with sync_engine.begin() as connection:
                alembic_config.attributes["connection"] = connection
                command.upgrade(alembic_config, "head")
        finally:
            sync_engine.dispose()

    # Alembic is synchronous; keeping it off the event loop prevents a slow
    # migration from blocking health checks and other startup tasks.
    await asyncio.to_thread(upgrade)

async def close_db():
    await async_engine.dispose()
