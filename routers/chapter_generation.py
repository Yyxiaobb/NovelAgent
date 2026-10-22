import uuid

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException

from fastapi.responses import StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession

from starlette import status

from agent import LLMConfigurationError, LLMError

from config.db_conf import AsyncSessionLocal, get_db

from config.queue_conf import abort_content_job, enqueue_content_job

from crud import projects

from crud import generation as generation_crud

from crud import story_memory as story_memory_crud

from models.users import User

from schemas.agent import (
    ChapterGenerationRequest,
    ChapterGenerationResponse,
    ChapterMemoryGenerationRequest,
    ChapterMemoryGenerationResponse,
    ChapterPlanGenerationRequest,
    ChapterPlanGenerationResponse,
)

from schemas.projects import ChapterMemory


from services.knowledge_rag import (
    EmbeddingConfigurationError,
    EmbeddingRequestError,
    format_retrieved_context,
    retrieve_knowledge,
)

from utils.auth import get_current_user

from utils.response import success_response

from utils.generation_telemetry import log_generation_metric


from services.agent_generation import (
    content_max_tokens as _content_max_tokens,
    json_candidate as _json_candidate,
    memory_max_tokens as _memory_max_tokens,
    plan_max_tokens as _plan_max_tokens,
    text_value as _text_value,
)

from services.chapter_generation import (
    build_context,
    sse,
)

from agent.prompts import get_prompt_template, render_prompt

from agent.runtime import run_agent

from agent.skills import load_skill
from services.generation_runtime import generation_client

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/projects/{project_id}/chapters/{chapter_id}/content", response_model=None)
async def generate_chapter_content(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    context_started = perf_counter()
    project, chapter, plan, prompt, citations = await build_context(db, project_id, chapter_id, user.id, payload)
    log_generation_metric(
        "context_built",
        "chapter_content",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt),
        expected_words=plan.expected_words,
    )
    try:
        async with generation_client() as client:
            model_started = perf_counter()
            content = (
                await client.achat(
                    [
                        {"role": "system", "content": get_prompt_template("chapter_content").system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=_content_max_tokens(plan.expected_words),
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                "chapter_content",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(content),
                model=client.model,
                expected_words=plan.expected_words,
            )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="章节生成暂时不可用，请稍后重试",
        ) from error

    if not content:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型未返回可用章节内容")
    return success_response(
        message="章节生成成功",
        data=ChapterGenerationResponse(
            project_id=project.id,
            chapter_id=chapter.id,
            expected_words=plan.expected_words,
            plan=plan,
            content=content,
            citations=citations,
        ),
    )


@router.post("/projects/{project_id}/chapters/{chapter_id}/content/stream")
async def stream_chapter_content(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    context_started = perf_counter()
    project, chapter, plan, prompt, citations = await build_context(db, project_id, chapter_id, user.id, payload)
    log_generation_metric(
        "context_built",
        "chapter_content_stream",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt),
        expected_words=plan.expected_words,
    )

    async def events():
        total = 0
        first_chunk_ms = None
        model_started = perf_counter()
        try:
            async with generation_client() as client:
                async for chunk in client.astream(
                    [
                        {"role": "system", "content": get_prompt_template("chapter_content").system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=_content_max_tokens(plan.expected_words),
                ):
                    if first_chunk_ms is None:
                        first_chunk_ms = (perf_counter() - model_started) * 1000
                    total += len(chunk)
                    yield sse("chunk", chunk)
            log_generation_metric(
                "model_stream_complete",
                "chapter_content",
                (perf_counter() - model_started) * 1000,
                first_chunk_ms=round(first_chunk_ms, 2) if first_chunk_ms is not None else None,
                prompt_chars=len(prompt),
                output_chars=total,
                model=client.model,
                expected_words=plan.expected_words,
            )
            if not total:
                yield sse("error", "模型未返回可用章节内容")
            else:
                yield sse(
                    "done",
                    {
                        "project_id": project.id,
                        "chapter_id": chapter.id,
                        "expected_words": plan.expected_words,
                        "plan": plan.model_dump(),
                        "citations": citations,
                    },
                )
        except LLMConfigurationError:
            yield sse("error", "智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL")
        except LLMError:
            yield sse("error", "章节生成暂时不可用，请稍后重试")

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/projects/{project_id}/chapters/{chapter_id}/content/jobs")
async def start_chapter_content_job(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await build_context(db, project_id, chapter_id, user.id, payload)
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


@router.get("/chapter-content/jobs/{job_id}")
async def get_chapter_content_job(job_id: str, user: User = Depends(get_current_user)):
    async with AsyncSessionLocal() as db:
        job = await generation_crud.get_job(db, job_id, user.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在或已过期")
    result = job.result or {}
    return success_response(
        message="获取生成任务状态成功",
        data={
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "content": job.output_content or "",
            "expected_words": result.get("expected_words"),
            "plan": result.get("plan"),
            "citations": result.get("citations", []),
            "error": job.error_message,
        },
    )


@router.get("/chapter-content/jobs")
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
        data=[
            {
                "job_id": job.id,
                "project_id": job.project_id,
                "chapter_id": job.chapter_id,
                "job_type": job.job_type,
                "status": job.status,
                "progress": job.progress,
                "content": job.output_content or "",
                "expected_words": (job.result or {}).get("expected_words"),
                "plan": (job.result or {}).get("plan"),
                "citations": (job.result or {}).get("citations", []),
                "error": job.error_message,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
            for job in jobs
        ],
    )


@router.post("/chapter-content/jobs/{job_id}/cancel")
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


@router.post("/chapter-content/jobs/{job_id}/retry")
async def retry_chapter_content_job(job_id: str, user: User = Depends(get_current_user)):
    """Create a fresh task from a failed or cancelled generation request."""
    async with AsyncSessionLocal() as db:
        source = await generation_crud.get_job(db, job_id, user.id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生成任务不存在或已过期")
        if source.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有失败或已取消的任务可以重试")
        payload = ChapterGenerationRequest.model_validate(source.input_payload or {})
        await build_context(db, source.project_id, source.chapter_id, user.id, payload)
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


@router.post("/projects/{project_id}/chapters/{chapter_id}/memory", response_model=None)
async def generate_chapter_memory(
    project_id: int,
    chapter_id: int,
    payload: ChapterMemoryGenerationRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    chapter = await projects.get_chapter(db, project_id, chapter_id, user.id)
    if project is None or chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品或章节不存在、已删除或不可访问")
    if not (chapter.content or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="章节正文为空，无法整理摘要")
    user_idea = payload.user_idea if payload else None
    context_started = perf_counter()
    memory_template, prompt = render_prompt(
        "chapter_memory",
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_outline=project.outline or "暂未提供",
        chapter_number=chapter.chapter_number,
        chapter_name=chapter.chaptername or "未命名章节",
        chapter_plan=chapter.plan or "未提供",
        user_idea=user_idea or "未提供",
        content=chapter.content,
    )
    log_generation_metric(
        "context_built",
        "chapter_memory",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt),
        input_content_chars=len(chapter.content),
    )
    try:
        async with generation_client() as client:
            model_started = perf_counter()
            raw = (
                await client.achat(
                    [
                        {"role": "system", "content": memory_template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=_memory_max_tokens(chapter.content),
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                "chapter_memory",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(raw),
                model=client.model,
                max_tokens=_memory_max_tokens(chapter.content),
            )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="章节摘要整理暂时不可用，请稍后重试"
        ) from error
    try:
        parsed = _json_candidate(raw)
        if not isinstance(parsed, dict):
            raise ValueError("memory must be an object")
        summary = _text_value(parsed.pop("summary"))
        memory = ChapterMemory.model_validate(
            {
                field: _text_value(parsed.get(field, "无"))
                for field in ("character_state", "setting_changes", "unresolved_threads", "timeline")
            }
        )
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="模型返回的章节记忆格式无效，请重试"
        ) from error
    persist_started = perf_counter()
    chapter.summary = summary
    chapter.memory = memory.model_dump()
    await db.commit()
    await db.refresh(chapter)
    await story_memory_crud.sync_extracted_memories(
        db,
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
        memory=memory.model_dump(),
    )
    log_generation_metric(
        "memory_persisted",
        "chapter_memory",
        (perf_counter() - persist_started) * 1000,
        summary_chars=len(summary),
    )
    return success_response(
        message="章节摘要已整理",
        data=ChapterMemoryGenerationResponse(
            project_id=project.id, chapter_id=chapter.id, summary=summary, memory=memory
        ),
    )


@router.post("/projects/{project_id}/chapters/{chapter_id}/plan", response_model=None)
async def generate_chapter_plan(
    project_id: int,
    chapter_id: int,
    payload: ChapterPlanGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    chapter = await projects.get_chapter(db, project_id, chapter_id, user.id)
    if project is None or chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品或章节不存在、已删除或不可访问")
    context_started = perf_counter()
    template, prompt = render_prompt(
        "chapter_plan",
        project_id=project.id,
        chapter_id=chapter.id,
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        project_outline=project.outline or "暂未提供",
        chapter_number=chapter.chapter_number,
        chapter_name=chapter.chaptername or "未命名章节",
        expected_words=payload.expected_words,
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
    )
    skill = load_skill("chapter-planning", task_type="chapter_plan")
    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db,
                user_id=user.id,
                knowledge_base_ids=payload.knowledge_base_ids,
                query="\n".join(
                    (
                        project.projectname or "",
                        chapter.chaptername or "",
                        project.outline or "",
                        payload.user_idea or "",
                        str(payload.expected_words),
                    )
                ),
            )
        except PermissionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except EmbeddingConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EmbeddingRequestError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        prompt += format_retrieved_context(citations)
    log_generation_metric(
        "context_built",
        "chapter_plan",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt) + len(template.system) + len(skill.instructions),
        expected_words=payload.expected_words,
    )
    try:
        async with generation_client() as client:
            model_started = perf_counter()
            raw = await run_agent(
                client,
                [
                    {
                        "role": "system",
                        "content": f"{template.system}\n\n创作 Skill（{skill.name} v{skill.version}）：\n{skill.instructions}",
                    },
                    {"role": "user", "content": prompt},
                ],
                db,
                project_id=project.id,
                user_id=user.id,
                temperature=0.4,
                max_tokens=_plan_max_tokens(payload.expected_words),
            )
            log_generation_metric(
                "agent_complete",
                "chapter_plan",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt) + len(template.system) + len(skill.instructions),
                output_chars=len(raw),
                model=client.model,
            )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="章节规划生成暂时不可用，请稍后重试"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Agent 规划过程未能完成，请重试") from error
    try:
        parsed = _json_candidate(raw)
        if not isinstance(parsed, dict):
            raise ValueError("plan must be an object")
        parsed = {
            **parsed,
            "objective": _text_value(parsed.get("objective", "")),
            "conflict": _text_value(parsed.get("conflict", "")),
            "key_events": _text_value(parsed.get("key_events", "")),
            "ending_hook": _text_value(parsed.get("ending_hook", "")),
            "expected_words": int(parsed.get("expected_words", payload.expected_words)),
        }
        plan = ChapterPlanGenerationResponse.model_validate(
            {
                "project_id": project.id,
                "chapter_id": chapter.id,
                "plan": parsed,
                "citations": citations,
            }
        )
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="模型返回的章节规划格式无效，请重试"
        ) from error
    return success_response(message="章节规划生成成功", data=plan)
