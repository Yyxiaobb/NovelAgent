import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from agent import LLMClient, LLMConfigurationError, LLMError, LLMRequestError
from config.db_conf import AsyncSessionLocal, get_db
from config.queue_conf import abort_content_job, enqueue_content_job
from crud import projects
from crud import generation as generation_crud
from crud import story_memory as story_memory_crud
from models.users import User
from schemas.agent import (
    ChapterGenerationRequest, ChapterGenerationResponse,
    ChapterMemoryGenerationRequest, ChapterMemoryGenerationResponse,
    ChapterPlanGenerationRequest, ChapterPlanGenerationResponse,
    OutlineGenerationRequest, OutlineGenerationResponse,
    ProjectFieldGenerationRequest, ProjectFieldGenerationResponse,
)
from schemas.projects import ChapterMemory
from utils.auth import get_current_user
from utils.response import success_response
from services.agent_generation import (
    PROJECT_TYPES as _PROJECT_TYPES,
    content_max_tokens as _content_max_tokens,
    json_candidate as _json_candidate,
    memory_max_tokens as _memory_max_tokens,
    outline_max_tokens as _outline_max_tokens,
    plan_max_tokens as _plan_max_tokens,
    text_value as _text_value,
)
from services.chapter_generation import (
    build_context,
    sse,
)


router = APIRouter(prefix="/api/agent", tags=["agent"])


def _generation_client(*, timeout: float | None = None) -> LLMClient:
    """Interactive generation should fail fast instead of retrying a slow upstream call."""
    return LLMClient(max_retries=0, timeout=timeout)


def _prompt(payload: ProjectFieldGenerationRequest) -> str:
    context = (
        f"作品名称：{payload.projectname or '未填写'}\n"
        f"作品简介：{payload.introduction or '未填写'}\n"
        f"作品类型：{payload.project_type or '未选择'}"
    )
    if payload.field == "projectname":
        instruction = "请生成一个有辨识度、适合小说封面的中文作品名，只返回作品名，不要引号、序号或解释。"
    elif payload.field == "introduction":
        instruction = "请生成一段 80 到 180 字的中文小说简介，包含主角、背景和核心冲突，只返回简介正文。"
    else:
        instruction = f"请从以下类型中选择最合适的一项，只返回类型名称：{_PROJECT_TYPES}。"
    return f"你是小说策划助手。\n{context}\n{instruction}"


def _outline_prompt(project, expected_words: int, user_idea: str | None = None) -> str:
    return (
        "你是一名专业的中文长篇小说策划编辑。请根据以下作品资料创作一份可用于后续分章写作的完整故事大纲。\n"
        f"作品名称：{project.projectname or '未命名作品'}\n"
        f"作品类型：{project.project_type or '未指定'}\n"
        f"作品简介：{project.introduction or '未提供'}\n"
        f"用户补充想法：{user_idea.strip() if user_idea and user_idea.strip() else '未提供'}\n"
        f"整部作品目标总字数：约 {expected_words} 字（仅用于规划分卷、节奏和情节体量，不是要求输出同等字数的大纲）\n\n"
        "要求：\n"
        "1. 大纲符合作品类型和简介，不擅自更改核心设定；补全必要的人物目标、冲突和世界规则。\n"
        "2. 以清晰标题组织：核心设定、主要人物、故事主线、分卷/阶段规划、关键转折与结局。\n"
        "3. 分卷/阶段数量和每阶段情节体量要匹配目标字数；给出建议卷数及每卷大致字数。\n"
        "4. 情节具体、前后连贯，明确人物变化、主要悬念及其回收，避免空泛套话。\n"
        "5. 大纲是写作规划，不是小说正文；控制篇幅，优先保留关键设定、人物目标、主线冲突、阶段节点和结局。\n"
        "6. 只输出中文大纲正文，不要写创作过程或额外说明。"
    )


@router.post("/project-field", response_model=None)
async def generate_project_field(
    payload: ProjectFieldGenerationRequest,
    _: User = Depends(get_current_user),
):
    try:
        async with _generation_client() as client:
            value = (await client.achat([
                {"role": "system", "content": "你输出的内容会直接填入表单，必须简洁、自然、符合要求。"},
                {"role": "user", "content": _prompt(payload)},
            ], temperature=0.7)).strip()
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
        ) from error
    except LLMRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="模型响应超时，请缩短补充想法或稍后重试",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="智能生成暂时不可用，请稍后重试",
        ) from error

    if not value:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型未返回可用内容")
    if payload.field == "project_type":
        value = next((item for item in _PROJECT_TYPES.split("、") if item in value), "其他")
    return success_response(
        message="智能生成成功",
        data=ProjectFieldGenerationResponse(field=payload.field, value=value),
    )


@router.post("/projects/{project_id}/outline", response_model=None)
async def generate_project_outline(
    project_id: int,
    payload: OutlineGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")

    try:
        async with _generation_client(timeout=120) as client:
            outline = (await client.achat([
                {"role": "system", "content": "你输出的内容将作为小说大纲保存，请严格遵守用户作品资料和格式要求。"},
                {"role": "user", "content": _outline_prompt(project, payload.expected_words, payload.user_idea)},
            ], temperature=0.5, max_tokens=_outline_max_tokens(payload.expected_words))).strip()
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
        ) from error
    except LLMRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="大纲生成响应超时，请稍后重试或减少补充想法",
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="大纲生成暂时不可用，请稍后重试",
        ) from error

    if not outline:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型未返回可用大纲")

    project.expected_words = payload.expected_words
    await db.flush()
    return success_response(
        message="大纲生成成功",
        data=OutlineGenerationResponse(
            project_id=project.id,
            expected_words=payload.expected_words,
            outline=outline,
        ),
    )


@router.post("/projects/{project_id}/chapters/{chapter_id}/content", response_model=None)
async def generate_chapter_content(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project, chapter, plan, prompt = await build_context(db, project_id, chapter_id, user.id, payload)
    try:
        async with _generation_client() as client:
            content = (await client.achat([
                {"role": "system", "content": "你输出的内容将作为小说章节草稿，请严格遵守作品设定，只输出正文。"},
                {"role": "user", "content": prompt},
            ], temperature=0.8, max_tokens=_content_max_tokens(plan.expected_words))).strip()
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
    project, chapter, plan, prompt = await build_context(db, project_id, chapter_id, user.id, payload)

    async def events():
        total = 0
        try:
            async with _generation_client() as client:
                async for chunk in client.astream([
                    {"role": "system", "content": "你输出的内容将作为小说章节草稿，只输出正文。"},
                    {"role": "user", "content": prompt},
                ], temperature=0.8, max_tokens=_content_max_tokens(plan.expected_words)):
                    total += len(chunk)
                    yield sse("chunk", chunk)
            if not total:
                yield sse("error", "模型未返回可用章节内容")
            else:
                yield sse("done", {"project_id": project.id, "chapter_id": chapter.id, "expected_words": plan.expected_words, "plan": plan.model_dump()})
        except LLMConfigurationError:
            yield sse("error", "智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL")
        except LLMError:
            yield sse("error", "章节生成暂时不可用，请稍后重试")

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
        db, job_id=job_id, user_id=user.id, project_id=project_id,
        chapter_id=chapter_id, payload=payload.model_dump(mode="json"),
    )
    try:
        await enqueue_content_job(job_id)
    except Exception as error:
        async with AsyncSessionLocal() as session:
            job = await generation_crud.get_job(session, job_id, user.id)
            if job:
                await generation_crud.update_job(
                    session, job, status="failed", error_message="后台队列暂时不可用，请检查 Redis 服务后重试",
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
    return success_response(message="获取生成任务状态成功", data={
        "job_id": job.id, "status": job.status, "progress": job.progress,
        "content": job.output_content or "", "expected_words": result.get("expected_words"),
        "plan": result.get("plan"), "error": job.error_message,
    })


@router.get("/chapter-content/jobs")
async def list_chapter_content_jobs(
    project_id: int | None = None,
    chapter_id: int | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    async with AsyncSessionLocal() as db:
        jobs = await generation_crud.list_jobs(
            db, user.id, project_id=project_id, chapter_id=chapter_id, limit=limit,
        )
    return success_response(message="获取生成任务列表成功", data=[
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
            "error": job.error_message,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
        for job in jobs
    ])


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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务已标记取消，但队列服务暂时不可用") from error
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
            db, job_id=new_job_id, user_id=user.id, project_id=source.project_id,
            chapter_id=source.chapter_id, payload=payload.model_dump(mode="json"),
        )
    try:
        await enqueue_content_job(new_job_id)
    except Exception as error:
        async with AsyncSessionLocal() as db:
            job = await generation_crud.get_job(db, new_job_id, user.id)
            if job:
                await generation_crud.update_job(
                    db, job, status="failed", error_message="后台队列暂时不可用，请检查 Redis 服务后重试",
                )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后台生成队列暂时不可用") from error
    return success_response(message="已重新创建章节生成任务", data={
        "job_id": new_job_id, "source_job_id": source.id, "status": "queued", "progress": 0,
    })


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
    prompt = (
        "你是一名小说 continuity 编辑。请从章节正文中提取可供后续章节使用的可靠记忆，只返回合法 JSON，不要 Markdown 代码块。\n"
        f"作品名称：{project.projectname or '未命名作品'}\n作品类型：{project.project_type or '未指定'}\n"
        f"作品大纲：{project.outline or '暂未提供'}\n章节编号：第 {chapter.chapter_number} 章\n"
        f"章节名称：{chapter.chaptername or '未命名章节'}\n章节规划：{chapter.plan or '未提供'}\n"
        f"用户补充说明：{user_idea or '未提供'}\n章节正文：\n{chapter.content}\n\n"
        "JSON 必须包含 summary、character_state、setting_changes、unresolved_threads、timeline 五个字符串字段。"
        "summary 用 100 到 300 字概括本章实际发生的事件；其余字段只记录正文明确出现的事实，未提及时写‘无’。"
    )
    try:
        async with _generation_client() as client:
            raw = (await client.achat([
                {"role": "system", "content": "你只输出合法 JSON，不要补充解释。"},
                {"role": "user", "content": prompt},
            ], temperature=0.2, max_tokens=_memory_max_tokens(chapter.content))).strip()
    except LLMConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL") from error
    except LLMError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="章节摘要整理暂时不可用，请稍后重试") from error
    try:
        parsed = _json_candidate(raw)
        if not isinstance(parsed, dict):
            raise ValueError("memory must be an object")
        summary = _text_value(parsed.pop("summary"))
        memory = ChapterMemory.model_validate({
            field: _text_value(parsed.get(field, "无"))
            for field in ("character_state", "setting_changes", "unresolved_threads", "timeline")
        })
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型返回的章节记忆格式无效，请重试") from error
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
    return success_response(
        message="章节摘要已整理",
        data=ChapterMemoryGenerationResponse(project_id=project.id, chapter_id=chapter.id, summary=summary, memory=memory),
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
    prompt = (
        "你是一名专业的中文小说策划编辑，请为指定章节制定可执行的章节规划。只返回 JSON，不要 Markdown 代码块。\n"
        f"作品名称：{project.projectname or '未命名作品'}\n作品类型：{project.project_type or '未指定'}\n"
        f"作品简介：{project.introduction or '未提供'}\n作品大纲：{project.outline or '暂未提供'}\n"
        f"章节编号：第 {chapter.chapter_number} 章\n章节名称：{chapter.chaptername or '未命名章节'}\n"
        f"目标字数：约 {payload.expected_words} 字\n用户想法：{payload.user_idea or '未提供'}\n\n"
        "JSON 必须包含字符串字段 objective、conflict、key_events、ending_hook，以及整数 expected_words；"
        "关键情节要有 3 到 6 个具体事件，结尾钩子要能推动下一章。"
    )
    try:
        async with _generation_client() as client:
            raw = (await client.achat([
                {"role": "system", "content": "你只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ], temperature=0.4, max_tokens=_plan_max_tokens(payload.expected_words))).strip()
    except LLMConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL") from error
    except LLMError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="章节规划生成暂时不可用，请稍后重试") from error
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
        plan = ChapterPlanGenerationResponse.model_validate({"project_id": project.id, "chapter_id": chapter.id, "plan": parsed})
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型返回的章节规划格式无效，请重试") from error
    return success_response(message="章节规划生成成功", data=plan)
