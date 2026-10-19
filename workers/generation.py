"""ARQ worker entry point for long-running novel generation."""

from arq.connections import RedisSettings

from config.db_conf import AsyncSessionLocal, close_db, init_db
from config.queue_conf import REDIS_URL
from crud import generation as generation_crud
from services.agent_generation import content_max_tokens
from services.chapter_generation import run_content_job
from services.generation_runtime import generation_client


async def generate_chapter_content(ctx: dict, job_id: str) -> None:
    await run_content_job(job_id, AsyncSessionLocal, generation_client, content_max_tokens)


async def startup(ctx: dict) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        pending = await generation_crud.list_pending_jobs(db, limit=500)
    for job in pending:
        # ARQ's stable job id prevents duplicate enqueue when another worker
        # still owns the job or when startup recovery is run more than once.
        await ctx["redis"].enqueue_job("generate_chapter_content", job.id, _job_id=job.id)


async def shutdown(ctx: dict) -> None:
    await close_db()


class WorkerSettings:
    functions = [generate_chapter_content]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    allow_abort_jobs = True
    max_jobs = 2
    job_timeout = 60 * 60
    max_tries = 1
