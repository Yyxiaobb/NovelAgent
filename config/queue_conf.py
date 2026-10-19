"""Redis-backed queue helpers for long-running generation jobs."""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@asynccontextmanager
async def get_queue_pool() -> AsyncIterator[ArqRedis]:
    pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    try:
        yield pool
    finally:
        await pool.aclose()


async def enqueue_content_job(job_id: str) -> bool:
    async with get_queue_pool() as pool:
        job = await pool.enqueue_job("generate_chapter_content", job_id, _job_id=job_id)
    return job is not None


async def abort_content_job(job_id: str) -> bool:
    async with get_queue_pool() as pool:
        return await Job(job_id, pool).abort()
