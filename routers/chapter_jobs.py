"""Background chapter generation job routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import AsyncSessionLocal, get_db
from config.queue_conf import abort_content_job, enqueue_content_job
from crud import generation as generation_crud
from crud import review_preferences as review_preferences_crud
from models.users import User
from schemas.agent import ChapterGenerationRequest
from services.chapter_generation import prepare_content_context
from services.generation_jobs import generation_job_payload
from utils.auth import get_current_user
from utils.response import success_response


chapter_jobs_router = APIRouter(tags=["agent"])


@chapter_jobs_router.post("/projects/{project_id}/chapters/{chapter_id}/content/jobs")
async def start_chapter_content_job(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload.review_preferences = await review_preferences_crud.resolve_preferences(db, user.id, project_id)
    await prepare_content_context(db, project_id, chapter_id, user.id, payload)
    job_id = uuid.uuid4().hex
    await generation_crud.create_chapter_content_job(
        db,
        job_id=job_id,
        user_id=user.id,
        project_id=project_id,
        chapter_id=chapter_id,
        payload=payload.model_dump(mode="json"),
    )
    try:
        await enqueue_content_job(job_id)
    except Exception as error:
        async with AsyncSessionLocal() as session:
            job = await generation_crud.get_job(session, job_id, user.id)
            if job:
                await generation_crud.update_job(
                    session,
                    job,
                    status="failed",
                    error_message="后台队列暂时不可用，请检查 Redis 服务后重试",
                )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后台生成队列暂时不可用") from error
    return success_response(message="章节生成任务已创建", data={"job_id": job_id, "status": "queued", "progress": 0})


@chapter_jobs_router.get("/chapter-content/jobs/{job_id}")
async def get_chapter_content_job(job_id: str, user: User = Depends(get_current_user)):
    async with AsyncSessionLocal() as db:
        job = await generation_crud.get_job(db, job_id, user.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在或已过期")
    return success_response(
        message="获取生成任务状态成功",
        data=generation_job_payload(job),
    )


@chapter_jobs_router.get("/chapter-content/jobs")
async def list_chapter_content_jobs(
    project_id: int | None = None,
    chapter_id: int | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    async with AsyncSessionLocal() as db:
        jobs = await generation_crud.list_jobs(
            db,
            user.id,
            project_id=project_id,
            chapter_id=chapter_id,
            limit=limit,
        )
    return success_response(
        message="获取生成任务列表成功",
        data=[generation_job_payload(job, include_scope=True) for job in jobs],
    )


@chapter_jobs_router.post("/chapter-content/jobs/{job_id}/cancel")
async def cancel_chapter_content_job(job_id: str, user: User = Depends(get_current_user)):
    async with AsyncSessionLocal() as db:
        job = await generation_crud.get_job(db, job_id, user.id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在或已过期")
        if job.status in {"completed", "failed", "cancelled"}:
            return success_response(message="任务已经结束", data={"job_id": job.id, "status": job.status})
        await generation_crud.update_job(db, job, status="cancelled", progress=job.progress)
    try:
        await abort_content_job(job_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务已标记取消，但队列服务暂时不可用"
        ) from error
    return success_response(message="生成任务已取消", data={"job_id": job_id, "status": "cancelled"})


@chapter_jobs_router.post("/chapter-content/jobs/{job_id}/retry")
async def retry_chapter_content_job(job_id: str, user: User = Depends(get_current_user)):
    """Create a fresh task from a failed or cancelled generation request."""
    async with AsyncSessionLocal() as db:
        source = await generation_crud.get_job(db, job_id, user.id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在或已过期")
        if source.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有失败或已取消的任务可以重试")
        payload = ChapterGenerationRequest.model_validate(source.input_payload or {})
        await prepare_content_context(db, source.project_id, source.chapter_id, user.id, payload)
        new_job_id = uuid.uuid4().hex
        await generation_crud.create_chapter_content_job(
            db,
            job_id=new_job_id,
            user_id=user.id,
            project_id=source.project_id,
            chapter_id=source.chapter_id,
            payload=payload.model_dump(mode="json"),
        )
    try:
        await enqueue_content_job(new_job_id)
    except Exception as error:
        async with AsyncSessionLocal() as db:
            job = await generation_crud.get_job(db, new_job_id, user.id)
            if job:
                await generation_crud.update_job(
                    db,
                    job,
                    status="failed",
                    error_message="后台队列暂时不可用，请检查 Redis 服务后重试",
                )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后台生成队列暂时不可用") from error
    return success_response(
        message="已重新创建章节生成任务",
        data={
            "job_id": new_job_id,
            "source_job_id": source.id,
            "status": "queued",
            "progress": 0,
        },
    )
