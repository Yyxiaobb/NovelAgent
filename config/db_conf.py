from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine

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
        finally:
            await session.close()
