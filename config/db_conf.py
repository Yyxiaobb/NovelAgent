from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

ASYNC_DATABASE_URL = "mysql+aiomysql://root:000314@localhost:3306/novel_agent?charset=utf8mb4"

# 创建异步引擎
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=True,
    pool_size = 10,
    max_overflow = 20,
)

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

async def init_db():
    """启动时建表(仅开发用)"""
    # 在这里 import 所有 model,保证它们已注册到 Base.metadata
    from models import users, projects  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "mysql":
            columns = await conn.run_sync(lambda sync_conn: {
                column["name"]: column
                for column in inspect(sync_conn).get_columns("project")
            })
            if "回收站" not in getattr(columns["status"]["type"], "enums", ()):
                await conn.execute(text(
                    "ALTER TABLE project "
                    "MODIFY COLUMN status "
                    "ENUM('连载中', '完结', '断更', '回收站') "
                    "NULL COMMENT '项目状态'"
                ))
            if "previous_status" not in columns:
                await conn.execute(text(
                    "ALTER TABLE project ADD COLUMN previous_status "
                    "VARCHAR(20) NULL COMMENT '移入回收站前的项目状态'"
                ))
            chapter_columns = await conn.run_sync(lambda sync_conn: {
                column["name"]
                for column in inspect(sync_conn).get_columns("chapters")
            })
            if "is_deleted" not in chapter_columns:
                await conn.execute(text(
                    "ALTER TABLE chapters ADD COLUMN is_deleted "
                    "BOOLEAN NOT NULL DEFAULT 0 COMMENT '是否已移入回收站'"
                ))

async def close_db():
    await async_engine.dispose()
