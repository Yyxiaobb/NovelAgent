import uuid
from datetime import datetime
from types import SimpleNamespace

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException

from fastapi.responses import StreamingResponse
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from starlette import status

from agent import LLMConfigurationError, LLMError, LLMRequestError

from config.db_conf import AsyncSessionLocal, get_db

from config.queue_conf import abort_content_job, enqueue_content_job

from crud import projects
from crud import versions as chapter_versions

from crud import generation as generation_crud

from crud import story_memory as story_memory_crud

from models.users import User
from models.projects import Chapter

from schemas.agent import (
    ChapterGenerationRequest,
    ChapterGenerationResponse,
    ChapterMemoryGenerationRequest,
    ChapterMemoryGenerationResponse,
    ChapterPlanGenerationRequest,
    ChapterPlanGenerationResponse,
    RollingChapterPlanGenerationRequest,
    RollingChapterPlanGenerationResponse,
    RollingChapterPlanItem,
)

from schemas.projects import ChapterPlan


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
    plan_max_tokens as _plan_max_tokens,
    text_value as _text_value,
)

from services.chapter_generation import (
    ContentQualityError,
    prepare_content_context,
    generate_content,
    generate_reviewed_content,
    review_enabled,
    stream_content,
    sse,
    validate_content_quality,
)
from services.chapter_memory_generation import generate_chapter_memory as generate_chapter_memory_for_chapter
from services.content_review import review_runtime_config

from services.story_memory import build_project_memory_context

from agent.prompts import render_prompt

from agent.runtime import run_agent

from agent.skills import load_skill
from services.generation_runtime import generation_client

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/review/config")
async def get_review_config(user: User = Depends(get_current_user)):
    """Expose safe review settings without returning credentials or service URLs."""
    return success_response(message="获取评审配置成功", data=review_runtime_config())


def _chapter_plan_prior_context(chapters: list, *, detailed_count: int = 3) -> str:
    """Build a tiered eight-chapter context without repeating tool summaries."""
    if not chapters:
        return "暂无前文摘要"
    detail_start = max(0, len(chapters) - detailed_count)
    sections: list[str] = []
    for index, item in enumerate(chapters):
        summary = (item.summary or "").strip()[:1200]
        plan = item.plan or {}
        if index >= detail_start:
            sections.append(
                f"第{item.chapter_number}章摘要：{summary or '暂无'}；"
                f"细纲目标：{plan.get('objective', '')[:500] or '暂无'}；"
                f"关键情节：{plan.get('key_events', '')[:700] or '暂无'}；"
                f"结尾钩子：{plan.get('ending_hook', '')[:400] or '暂无'}"
            )
        else:
            memory = item.memory or {}
            sections.append(
                f"第{item.chapter_number}章摘要：{summary or '暂无'}；"
                f"未解决线索：{str(memory.get('unresolved_threads', '')).strip()[:500] or '暂无'}；"
                f"人物状态：{str(memory.get('character_state', '')).strip()[:500] or '暂无'}"
            )
    return "\n".join(sections)


@router.post("/projects/{project_id}/chapters/{chapter_id}/content", response_model=None)
async def generate_chapter_content(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    context_started = perf_counter()
    context = await prepare_content_context(db, project_id, chapter_id, user.id, payload)
    project, chapter, plan, prompt, citations = (
        context.project, context.chapter, context.plan, context.prompt, context.citations
    )
    log_generation_metric(
        "context_built",
        "chapter_content",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt),
        expected_words=plan.expected_words,
    )
    try:
        model_started = perf_counter()
        content, model, review_result = await generate_reviewed_content(
            context, generation_client, _content_max_tokens,
        )
        log_generation_metric(
            "model_complete",
            "chapter_content",
            (perf_counter() - model_started) * 1000,
            prompt_chars=len(prompt),
            output_chars=len(content),
            model=model,
            expected_words=plan.expected_words,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="章节生成暂时不可用，请稍后重试",
        ) from error
    except ContentQualityError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

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
            **(review_result.metadata() if review_result else {}),
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
    context = await prepare_content_context(db, project_id, chapter_id, user.id, payload)
    project, chapter, plan, prompt, citations = (
        context.project, context.chapter, context.plan, context.prompt, context.citations
    )
    log_generation_metric(
        "context_built",
        "chapter_content_stream",
        (perf_counter() - context_started) * 1000,
        prompt_chars=len(prompt),
        expected_words=plan.expected_words,
    )

    async def events():
        total = 0
        generated_parts = []
        first_chunk_ms = None
        model_started = perf_counter()
        client_model = None

        def remember_client(client):
            nonlocal client_model
            client_model = client.model

        try:
            if review_enabled():
                reviewed_content, reviewed_model, review_result = await generate_reviewed_content(
                    context, generation_client, _content_max_tokens,
                )
                client_model = reviewed_model
                generated_parts.append(reviewed_content)
                total = len(reviewed_content)
                yield sse("chunk", reviewed_content)
                review_metadata = review_result.metadata() if review_result else {}
                yield sse(
                    "done",
                    {
                        "project_id": project.id,
                        "chapter_id": chapter.id,
                        "expected_words": plan.expected_words,
                        "plan": plan.model_dump(),
                        "citations": citations,
                        **review_metadata,
                    },
                )
                return
            async for chunk in stream_content(
                context, generation_client, _content_max_tokens, on_client=remember_client
            ):
                if first_chunk_ms is None:
                    first_chunk_ms = (perf_counter() - model_started) * 1000
                total += len(chunk)
                generated_parts.append(chunk)
                yield sse("chunk", chunk)
            log_generation_metric(
                "model_stream_complete",
                "chapter_content",
                (perf_counter() - model_started) * 1000,
                first_chunk_ms=round(first_chunk_ms, 2) if first_chunk_ms is not None else None,
                prompt_chars=len(prompt),
                output_chars=total,
                model=client_model,
                expected_words=plan.expected_words,
            )
            validate_content_quality("".join(generated_parts), plan.expected_words)
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
        except ContentQualityError as error:
            yield sse("error", str(error))
        except LLMConfigurationError:
            yield sse("error", "智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL")
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
            "generation_info": {
                key: result.get(key)
                for key in (
                    "model", "prompt_template_id", "prompt_template_version", "segments", "quality_check",
                    "review_enabled", "review_rounds", "review_final_score", "review_stop_reason", "review_error", "review_history", "revision_decisions",
                )
                if result.get(key) is not None
            },
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
                "generation_info": {
                    key: (job.result or {}).get(key)
                    for key in (
                        "model", "prompt_template_id", "prompt_template_version", "segments", "quality_check",
                        "review_enabled", "review_rounds", "review_final_score", "review_stop_reason", "review_error", "review_history", "revision_decisions",
                    )
                    if (job.result or {}).get(key) is not None
                },
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


@router.post("/projects/{project_id}/chapters/{chapter_id}/memory", response_model=None)
async def generate_chapter_memory(
    project_id: int,
    chapter_id: int,
    payload: ChapterMemoryGenerationRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    summary, memory = await generate_chapter_memory_for_chapter(
        db, project_id, chapter_id, user.id, payload.user_idea if payload else None,
    )
    return success_response(
        message="章节摘要已整理",
        data=ChapterMemoryGenerationResponse(
            project_id=project_id, chapter_id=chapter_id, summary=summary, memory=memory
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
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        project_outline=project.outline or "暂未提供",
        chapter_number=chapter.chapter_number,
        expected_words=payload.expected_words,
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
    )
    volumes = await projects.get_outline_volumes(db, project.id)
    current_volume = projects.resolve_outline_volume(volumes, getattr(chapter, "volume_id", None))
    if current_volume and current_volume.outline:
        prompt += (
            "\n\n当前卷纲（生成后请对照此纲判断本章细纲是否完成本卷目标；"
            "不依据章节编号或字数判断）：\n" + current_volume.outline[:10000]
        )
    else:
        prompt += "\n\n当前没有可用卷纲；volume_complete 必须为 false。"

    prior_chapters = await projects.get_prior_chapter_memories(db, project.id, chapter.chapter_number, limit=8)
    prompt += (
        "\n\n前文最近 8 章连续性资料（最近 3 章保留细纲，较早章节压缩为摘要和结构化线索）：\n"
        + _chapter_plan_prior_context(prior_chapters)
    )

    memories = await story_memory_crud.list_active_project_memories(db, project.id)
    memory_context = build_project_memory_context(
        memories,
        " ".join((payload.user_idea or "", project.project_type or "")),
        current_chapter_id=chapter.id,
    )
    prompt += f"\n\n与本章相关的已确认长期记忆：\n{memory_context}"
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
                        project.project_type or "",
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
            detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
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
                "volume_id": current_volume.id if current_volume else None,
                "volume_complete": bool(current_volume is not None and parsed.get("volume_complete") is True),
                "volume_completion_note": _text_value(parsed.get("volume_completion_note", "")) or None,
            }
        )
    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="模型返回的章节规划格式无效，请重试"
        ) from error
    return success_response(message="章节规划生成成功", data=plan)


@router.post("/projects/{project_id}/chapters/rolling-plan", response_model=None)
async def generate_rolling_chapter_plans(
    project_id: int,
    payload: RollingChapterPlanGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate one consecutive batch of chapter plans with a single model call."""
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    if not payload.chapter_ids and not payload.chapter_numbers:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少指定一个目标章节")
    if len(set(payload.chapter_ids)) != len(payload.chapter_ids) or len(set(payload.chapter_numbers)) != len(payload.chapter_numbers):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="章节不能重复")

    active_chapters = await projects.get_project_chapters(db, project.id, user.id) or []
    active_by_id = {chapter.id: chapter for chapter in active_chapters}
    active_by_number = {chapter.chapter_number: chapter for chapter in active_chapters}
    for chapter_id in payload.chapter_ids:
        if chapter_id not in active_by_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标章节不存在或不可访问")

    # The caller can send only existing IDs (legacy behavior), or a complete
    # batch of chapter numbers. For missing numbers, use temporary negative IDs
    # while generating; those rows are created only after model validation.
    requested_numbers = list(payload.chapter_numbers)
    if not requested_numbers:
        requested_numbers = [active_by_id[chapter_id].chapter_number for chapter_id in payload.chapter_ids]
    selected_by_number = {
        active_by_id[chapter_id].chapter_number: active_by_id[chapter_id]
        for chapter_id in payload.chapter_ids
    }
    occupied_numbers = set(
        await db.scalars(select(Chapter.chapter_number).where(Chapter.project_id == project.id))
    )
    chapters = []
    for index, requested_number in enumerate(requested_numbers):
        chapter_number = requested_number
        existing = selected_by_number.get(chapter_number) or active_by_number.get(chapter_number)
        if existing is None:
            while chapter_number in occupied_numbers:
                chapter_number += 1
            occupied_numbers.add(chapter_number)
            chapter_name = f"第{chapter_number}章"
            chapters.append(SimpleNamespace(
                id=-chapter_number,
                chapter_number=chapter_number,
                chaptername=chapter_name,
                content=None,
                summary=None,
                plan=None,
                memory=None,
                is_virtual=True,
            ))
        else:
            chapters.append(existing)
    if not chapters:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少指定一个目标章节")
    chapters.sort(key=lambda item: (item.chapter_number, item.id))

    context_started = perf_counter()
    volumes = await projects.get_outline_volumes(db, project.id)
    assigned_volume_ids = {chapter.volume_id for chapter in chapters if getattr(chapter, "volume_id", None)}
    if len(assigned_volume_ids) > 1:
        raise HTTPException(status_code=409, detail="滚动细纲目标章节需属于同一卷")
    preferred_volume_id = next(iter(assigned_volume_ids), None)
    current_volume = projects.resolve_outline_volume(volumes, preferred_volume_id)
    ordered_groups = [{"volume": current_volume, "chapters": chapters}]
    chapter_specs = "\n".join(
        f"- chapter_id={chapter.id}，第{chapter.chapter_number}章，"
        f"已有摘要：{(chapter.summary or '暂无')[:800]}，已有细纲：{'有' if chapter.plan else '无'}"
        for chapter in chapters
    )
    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db, user_id=user.id, knowledge_base_ids=payload.knowledge_base_ids,
                query="\n".join((project.project_type or "", project.outline or "", chapter_specs)),
            )
        except PermissionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except EmbeddingConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EmbeddingRequestError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
    knowledge_context = format_retrieved_context(citations)
    skill = load_skill("chapter-planning", task_type="chapter_plan")
    normalized = []
    volume_complete = False
    volume_completion_note = None
    try:
        for group in ordered_groups:
            group_chapters = group["chapters"]
            group_first = group_chapters[0]
            current_volume = group["volume"]
            volume_context = (
                (current_volume.outline or "暂无当前卷纲")[:10000]
                if current_volume is not None
                else "未配置可匹配的卷纲；仅依据作品总纲与前文连续性规划"
            )
            prior_chapters = await projects.get_prior_chapter_memories(
                db, project.id, group_first.chapter_number, limit=8,
            )
            prior_context = _chapter_plan_prior_context(prior_chapters)
            group_specs = "\n".join(
                f"- chapter_id={chapter.id}，第{chapter.chapter_number}章，"
                f"已有摘要：{(chapter.summary or '暂无')[:800]}，已有细纲：{'有' if chapter.plan else '无'}"
                for chapter in group_chapters
            )
            memories = await story_memory_crud.list_active_project_memories(db, project.id)
            memory_context = build_project_memory_context(
                memories, project.project_type or "", current_chapter_id=group_first.id,
            )
            template, prompt = render_prompt(
                "chapter_plan_batch", project_id=project.id,
                project_type=project.project_type or "未指定",
                project_introduction=project.introduction or "未提供",
                project_outline=project.outline or "暂未提供",
                volume_context=volume_context, prior_context=prior_context,
                chapter_specs=group_specs,
                user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
            )
            prompt += f"\n\n与本批章节相关的已确认长期记忆：\n{memory_context}{knowledge_context}"
            log_generation_metric(
                "context_built", "chapter_plan_batch", (perf_counter() - context_started) * 1000,
                prompt_chars=len(prompt) + len(template.system) + len(skill.instructions),
                expected_words=payload.expected_words * len(group_chapters),
            )
            async with generation_client() as client:
                model_started = perf_counter()
                messages = [
                    {"role": "system", "content": f"{template.system}\n\n创作 Skill（{skill.name} v{skill.version}）：\n{skill.instructions}"},
                    {"role": "user", "content": prompt},
                ]
                # A rolling batch advances one active volume at a time.
                if hasattr(client, "achat"):
                    raw = await client.achat(messages, temperature=0.2, max_tokens=8000)
                else:
                    raw = await run_agent(
                        client, messages, db, project_id=project.id, user_id=user.id,
                        temperature=0.4, max_tokens=8000,
                    )
                log_generation_metric(
                    "agent_complete", "chapter_plan_batch", (perf_counter() - model_started) * 1000,
                    prompt_chars=len(prompt) + len(template.system) + len(skill.instructions),
                    output_chars=len(raw), model=client.model,
                )
            parsed = _json_candidate(raw)
            if isinstance(parsed, dict):
                volume_complete = bool(current_volume is not None and parsed.get("volume_complete") is True)
                volume_completion_note = _text_value(parsed.get("volume_completion_note", "")) or None
            raw_plans = parsed.get("plans") if isinstance(parsed, dict) else None
            if not isinstance(raw_plans, list):
                raise ValueError("plans must be a list")
            by_id = {chapter.id: chapter for chapter in group_chapters}
            group_normalized = []
            for item in raw_plans:
                if not isinstance(item, dict):
                    continue
                try:
                    chapter_id = int(item.get("chapter_id"))
                except (TypeError, ValueError):
                    chapter_id = 0
                chapter = by_id.get(chapter_id)
                if chapter is None:
                    try:
                        chapter_number = int(item.get("chapter_number"))
                    except (TypeError, ValueError):
                        chapter_number = None
                    if chapter_number is not None:
                        chapter = next((candidate for candidate in group_chapters if candidate.chapter_number == chapter_number), None)
                if chapter is None:
                    continue
                plan_data = item.get("plan") if isinstance(item.get("plan"), dict) else item
                plan_data = {
                    **plan_data,
                    "objective": _text_value(plan_data.get("objective", "")),
                    "conflict": _text_value(plan_data.get("conflict", "")),
                    "key_events": _text_value(plan_data.get("key_events", "")),
                    "ending_hook": _text_value(plan_data.get("ending_hook", "")),
                    "expected_words": int(plan_data.get("expected_words", payload.expected_words)),
                }
                group_normalized.append(RollingChapterPlanItem(
                    chapter_id=chapter.id, chapter_number=chapter.chapter_number,
                    chapter_name=chapter.chaptername or f"第{chapter.chapter_number}章",
                    plan=ChapterPlan.model_validate(plan_data),
                ))
            if len(group_normalized) != len(group_chapters) or {item.chapter_id for item in group_normalized} != set(by_id):
                raise ValueError("batch plans are incomplete")
            normalized.extend(group_normalized)
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL") from error
    except LLMRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail="滚动细纲规划暂时不可用，请稍后重试") from error
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(status_code=502, detail="模型返回的批量章节规划格式无效，请重试") from error

    normalized.sort(key=lambda item: item.chapter_number)
    result = RollingChapterPlanGenerationResponse(
        project_id=project.id, plans=normalized, citations=citations,
        volume_id=current_volume.id if current_volume else None,
        volume_complete=volume_complete,
        volume_completion_note=volume_completion_note,
    )

    # When chapter_numbers are supplied this endpoint owns the complete
    # rolling-plan operation. Persist only after the model response has passed
    # validation, so model/network/format failures leave no newly created rows.
    if payload.chapter_numbers:
        virtual_chapters = {chapter.id: chapter for chapter in chapters if getattr(chapter, "is_virtual", False)}
        for item in result.plans:
            if item.chapter_id in virtual_chapters:
                virtual = virtual_chapters[item.chapter_id]
                chapter = Chapter(
                    project_id=project.id,
                    chapter_number=virtual.chapter_number,
                    chaptername=item.chapter_name or virtual.chaptername,
                    plan=item.plan.model_dump(),
                    volume_id=result.volume_id,
                )
                db.add(chapter)
                await db.flush()
                item.chapter_id = chapter.id
            else:
                chapter = active_by_id.get(item.chapter_id)
                if chapter is None:
                    raise HTTPException(status_code=404, detail="目标章节不存在或不可访问")
                await chapter_versions.add_snapshot(db, chapter, user.id, source="plan_edit")
                chapter.plan = item.plan.model_dump()
                chapter.volume_id = result.volume_id
        if result.volume_complete and result.volume_id:
            volume = next((item for item in volumes if item.id == result.volume_id), None)
            if volume is not None:
                volume.is_completed = True
                volume.completion_note = result.volume_completion_note
                volume.completed_at = datetime.now()
        await projects.recalculate_project_stats(db, project, lock=True)
        await db.commit()
        await db.refresh(project)
    return success_response(message="滚动细纲规划成功", data=result)
