import asyncio
import json
import re
import math
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent import LLMConfigurationError, LLMError, LLMRequestError
from agent.prompts import get_prompt_template, render_prompt
from crud import generation as generation_crud
from crud import projects
from crud import story_memory as story_memory_crud
from models.generation import GenerationJob
from schemas.agent import ChapterGenerationRequest
from schemas.projects import ChapterPlan
from services.story_memory import build_project_memory_context, build_story_memory
from services.knowledge_rag import (
    EmbeddingConfigurationError,
    EmbeddingRequestError,
    format_retrieved_context,
    retrieve_knowledge,
)
from services.content_review import (
    ReviewLoopResult,
    revision_messages,
    review_enabled,
    run_review_loop,
)
from services.generation_runtime import reviewer_client


@dataclass(frozen=True)
class ChapterContentContext:
    """All data required to generate one chapter.

    Keeping this object independent from the transport layer means synchronous,
    streaming, and queued generation use exactly the same prompt and citations.
    """

    project: Any
    chapter: Any
    plan: ChapterPlan
    prompt: str
    citations: list[Any]
    volume_context: str = ""
    prior_context: str = ""

    @property
    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": get_prompt_template("chapter_content").system},
            {"role": "user", "content": self.prompt},
        ]


class ContentQualityError(ValueError):
    """The model returned output that is unsafe or unusable as chapter prose."""


_META_OPENERS = re.compile(
    r"^(?:以下是(?:正文|章节|内容)|当然[，,]\s*(?:以下|作为人工智能)|写作说明[:：]?|正文如下[:：]?|作为(?:一个)?(?:AI|人工智能))",
    re.IGNORECASE,
)
_PROMPT_LEAKS = ("system prompt", "系统提示词", "你是一个专业的小说创作助手")
BACKGROUND_GENERATION_ATTEMPTS = 2
MAX_WORDS_PER_SEGMENT = 8000
MAX_PROMPT_CHARACTERS = 48_000


def _limit_context(value: str, max_chars: int) -> str:
    value = value or ""
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}\n（上下文已截断，省略 {omitted} 字）"


def _fit_prompt_budget(prompt: str) -> str:
    """Keep the prompt within a conservative approximate token budget."""
    if len(prompt) <= MAX_PROMPT_CHARACTERS:
        return prompt
    marker = "\n\n（上下文预算限制：中间部分已省略）\n\n"
    remaining = MAX_PROMPT_CHARACTERS - len(marker)
    head_size = remaining * 3 // 4
    tail_size = remaining - head_size
    return f"{prompt[:head_size]}{marker}{prompt[-tail_size:]}"


def is_retryable_generation_error(error: LLMRequestError) -> bool:
    """Only retry transient provider/network failures for durable background jobs."""
    return (
        error.status_code is None
        or error.status_code in {408, 409, 425, 429}
        or 500 <= error.status_code < 600
    )


def validate_content_quality(content: str, expected_words: int) -> None:
    """Reject common generation failures consistently across all transports."""
    normalized = content.strip()
    if not normalized:
        raise ContentQualityError("模型未返回可用章节内容")
    minimum_length = min(200, max(80, round(expected_words * 0.1)))
    if len(normalized) < minimum_length:
        raise ContentQualityError(f"正文长度明显不足（至少需要约 {minimum_length} 字）")
    if "```" in normalized:
        raise ContentQualityError("正文包含 Markdown 代码围栏")
    if _META_OPENERS.search(normalized):
        raise ContentQualityError("模型返回了写作说明，请重新生成正文")
    lowered = normalized.casefold()
    if any(marker.casefold() in lowered for marker in _PROMPT_LEAKS):
        raise ContentQualityError("正文疑似包含系统提示内容")


def build_content_segments(context: ChapterContentContext) -> list[tuple[int, str]]:
    """Split unusually long chapters into bounded narrative sections.

    Regular chapters keep the original one-request behavior. Long chapters use
    the ordered key events as scene anchors and receive the preceding scene tail
    as continuity context.
    """
    segment_count = math.ceil(context.plan.expected_words / MAX_WORDS_PER_SEGMENT)
    if segment_count <= 1:
        return [(context.plan.expected_words, "")]
    events = [
        part.strip(" \t-•、")
        for part in re.split(r"[\n。；;，、]+", context.plan.key_events)
        if part.strip(" \t-•、")
    ]
    per_segment = math.ceil(context.plan.expected_words / segment_count)
    event_groups = [events[index::segment_count] for index in range(segment_count)]
    return [
        (
            min(per_segment, context.plan.expected_words - index * per_segment),
            "；".join(group) or f"围绕本章目标推进第 {index + 1} 段情节",
        )
        for index, group in enumerate(event_groups)
    ]


def _segment_messages(context: ChapterContentContext, index: int, count: int, events: str, previous: str):
    if count <= 1:
        return context.messages
    instructions = (
        f"\n\n分段创作要求：这是本章第 {index + 1}/{count} 段，目标约 "
        f"{math.ceil(context.plan.expected_words / count)} 字。只写本段正文，不要重复前文。"
        f"\n本段应推进的关键事件：{events or context.plan.key_events}"
    )
    if previous:
        instructions += f"\n上一段结尾（用于衔接，不要复述）：\n{previous[-1200:]}"
    return [
        context.messages[0],
        {"role": "user", "content": context.prompt + instructions},
    ]


async def prepare_content_context(
    db: AsyncSession,
    project_id: int,
    chapter_id: int,
    user_id: int,
    payload: ChapterGenerationRequest,
) -> ChapterContentContext:
    project = await projects.get_project(db, project_id, user_id)
    chapter = await projects.get_chapter(db, project_id, chapter_id, user_id)
    if project is None or chapter is None:
        raise HTTPException(status_code=404, detail="作品或章节不存在、已删除或不可访问")
    plan = payload.plan or (ChapterPlan.model_validate(chapter.plan) if chapter.plan else ChapterPlan(
        objective="推进本章故事并完成章节目标", conflict="主角面对当前情节中的核心阻碍",
        key_events="围绕作品大纲展开本章关键事件", ending_hook="留下推动下一章的悬念",
        expected_words=payload.expected_words or 3000,
    ))
    volumes = await projects.get_outline_volumes(db, project.id)
    current_volume = projects.resolve_outline_volume(
        volumes, getattr(chapter, "volume_id", None), active_only=False,
    )
    volume_context = (
        (current_volume.outline or "卷纲尚未填写")[:10000]
        if current_volume is not None
        else "当前章节尚未匹配到卷纲；依据作品总纲与前文连续性创作"
    )
    prior_chapters = await projects.get_prior_chapter_memories(db, project.id, chapter.chapter_number)
    memory_chapters = await projects.get_story_memory_chapters(db, project.id, chapter.chapter_number)
    prior_context = "\n".join(
        f"第 {item.chapter_number} 章摘要：{item.summary}\n"
        f"人物状态：{(item.memory or {}).get('character_state', '未记录')}\n"
        f"未解决线索：{(item.memory or {}).get('unresolved_threads', '未记录')}"
        for item in prior_chapters if item.summary
    ) or "暂无已整理的前文摘要"
    story_memory = build_story_memory(memory_chapters)
    project_memories = await story_memory_crud.list_active_project_memories(db, project.id)
    memory_query = "\n".join((
        plan.objective, plan.conflict, plan.key_events,
        plan.ending_hook, payload.user_idea or "",
    ))
    project_memory_context = build_project_memory_context(
        project_memories, memory_query, current_chapter_id=chapter.id,
    )
    _, prompt = render_prompt(
        "chapter_content",
        project_type=project.project_type or "未指定",
        project_introduction=_limit_context(project.introduction or "未提供", 2000),
        project_outline=_limit_context(project.outline or "暂未提供，请依据简介自然展开", 12000),
        current_state=_limit_context(project.current_state_markdown or "尚无当前状态记录", 8000),
        volume_context=_limit_context(volume_context, 10000),
        prior_context=_limit_context(prior_context, 6000),
        story_memory=_limit_context(story_memory, 6000),
        project_memory_context=_limit_context(project_memory_context, 6000),
        plan=plan.model_dump(),
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
        chapter_number=chapter.chapter_number,
        expected_words=plan.expected_words,
        objective=plan.objective,
        conflict=plan.conflict,
        key_events=plan.key_events,
        ending_hook=plan.ending_hook,
    )
    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db, user_id=user_id, knowledge_base_ids=payload.knowledge_base_ids,
                query="\n".join((project.project_type or "",
                                 plan.objective, plan.conflict, plan.key_events, payload.user_idea or "")),
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
    prompt = _fit_prompt_budget(prompt)
    return ChapterContentContext(
        project=project,
        chapter=chapter,
        plan=plan,
        prompt=prompt,
        citations=citations,
        volume_context=volume_context,
        prior_context=prior_context,
    )


async def build_context(db: AsyncSession, project_id: int, chapter_id: int, user_id: int, payload: ChapterGenerationRequest):
    """Backward-compatible tuple API for callers that still need unpacking."""
    context = await prepare_content_context(db, project_id, chapter_id, user_id, payload)
    return context.project, context.chapter, context.plan, context.prompt, context.citations


async def _generate_complete_with_client(
    context: ChapterContentContext,
    client: Any,
    content_token_fn: Callable[[int], int],
) -> str:
    segments = build_content_segments(context)
    outputs: list[str] = []
    for index, (segment_words, events) in enumerate(segments):
        messages = _segment_messages(context, index, len(segments), events, "\n".join(outputs))
        content = (await client.achat(
            messages, temperature=0.8, max_tokens=content_token_fn(segment_words),
        )).strip()
        try:
            validate_content_quality(content, segment_words)
        except ContentQualityError as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"刚才的输出未通过正文质量检查：{first_error}。"
                        f"请直接重写本段完整正文，目标约 {segment_words} 字，"
                        "不要添加说明、代码围栏或提示词内容。"
                    ),
                },
            ]
            content = (await client.achat(
                repair_messages,
                temperature=0.55,
                max_tokens=content_token_fn(segment_words),
            )).strip()
            validate_content_quality(content, segment_words)
        outputs.append(content)
    complete_content = "\n\n".join(outputs)
    validate_content_quality(complete_content, context.plan.expected_words)
    return complete_content


async def generate_content(
    context: ChapterContentContext,
    client_factory: Callable,
    content_token_fn: Callable[[int], int],
) -> tuple[str, str]:
    """Generate a complete chapter using the shared content contract.

    Returns ``(content, model_name)`` so API callers can keep their telemetry
    without duplicating client lifecycle and request construction.
    """
    async with client_factory() as client:
        return await _generate_complete_with_client(context, client, content_token_fn), client.model


async def generate_reviewed_content(
    context: ChapterContentContext,
    client_factory: Callable,
    content_token_fn: Callable[[int], int],
    *,
    on_review_iteration: Callable[[Any], Awaitable[None]] | None = None,
) -> tuple[str, str, ReviewLoopResult | None]:
    """Generate content and optionally run the bounded editorial review loop."""
    if not review_enabled():
        content, model = await generate_content(context, client_factory, content_token_fn)
        return content, model, None

    model_name: str | None = None

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def tracked_client_factory():
        nonlocal model_name
        async with client_factory() as client:
            model_name = client.model
            yield client

    async def generate_candidate(client: Any, previous: str | None, review: Any | None) -> str:
        if previous is None:
            return await _generate_complete_with_client(context, client, content_token_fn)
        messages = revision_messages(context, previous, review)
        revised = (await client.achat(
            messages,
            temperature=0.7,
            max_tokens=content_token_fn(context.plan.expected_words),
        )).strip()
        validate_content_quality(revised, context.plan.expected_words)
        return revised

    async with client_factory() as initial_client:
        model_name = initial_client.model
        initial_content = await _generate_complete_with_client(context, initial_client, content_token_fn)
    try:
        result = await run_review_loop(
            context,
            tracked_client_factory,
            generate_candidate,
            lambda content: validate_content_quality(content, context.plan.expected_words),
            reviewer_client_factory=reviewer_client,
            initial_content=initial_content,
            on_iteration=on_review_iteration,
        )
    except Exception as error:
        if isinstance(error, ContentQualityError):
            raise
        # A reviewer outage must not discard a valid generated draft. Return it
        # with an explicit degraded result so callers can surface the reason.
        degraded = ReviewLoopResult(
            content=initial_content, review=None, history=[], rounds=0,
            stop_reason="review_unavailable", review_error="评论员暂时不可用，已返回未评审初稿",
        )
        return initial_content, model_name or "unknown", degraded
    return result.content, model_name or "unknown", result


async def stream_content(
    context: ChapterContentContext,
    client_factory: Callable,
    content_token_fn: Callable[[int], int],
    *,
    on_client: Callable[[Any], None] | None = None,
) -> AsyncIterator[str]:
    """Yield chapter text chunks using the same request as sync generation."""
    async with client_factory() as client:
        if on_client is not None:
            on_client(client)
        segments = build_content_segments(context)
        outputs: list[str] = []
        for index, (segment_words, events) in enumerate(segments):
            if index:
                yield "\n\n"
            messages = _segment_messages(context, index, len(segments), events, "\n".join(outputs))
            current_parts: list[str] = []
            async for chunk in client.astream(
                messages,
                temperature=0.8,
                max_tokens=content_token_fn(segment_words),
            ):
                current_parts.append(chunk)
                yield chunk
            outputs.append("".join(current_parts))


def sse(event: str, data: Any) -> str:
    return f"data: {json.dumps({'event': event, 'data': data}, ensure_ascii=False)}\n\n"


async def run_content_job(
    job_id: str,
    session_factory: async_sessionmaker,
    client_factory: Callable,
    content_token_fn: Callable[[int], int],
):
    try:
        async with session_factory() as db:
            job = await db.get(GenerationJob, job_id)
            if job is None or job.status == "cancelled":
                return
            if not await generation_crud.start_job_if_active(db, job_id):
                return
            payload = ChapterGenerationRequest.model_validate(job.input_payload or {})
            context = await prepare_content_context(
                db, job.project_id, job.chapter_id, job.user_id, payload,
            )
            parts: list[str] = []
            last_persisted = asyncio.get_running_loop().time()
            model_name = None

            if review_enabled():
                reviewed_content = None
                review_result = None
                persisted_review_history: list[dict[str, Any]] = []

                async def persist_review_iteration(iteration: Any) -> None:
                    current_status = await db.scalar(
                        select(GenerationJob.status).where(GenerationJob.id == job_id)
                    )
                    if current_status == "cancelled":
                        raise asyncio.CancelledError
                    persisted_review_history.append(iteration.as_dict())
                    job.progress = min(95, 20 + iteration.round * 25)
                    job.result = {
                        **(job.result or {}),
                        "review_enabled": True,
                        "review_rounds": iteration.round,
                        "review_final_score": iteration.score,
                        "review_history": persisted_review_history,
                    }
                    await db.commit()

                for attempt in range(BACKGROUND_GENERATION_ATTEMPTS):
                    current_status = await db.scalar(
                        select(GenerationJob.status).where(GenerationJob.id == job_id)
                    )
                    if current_status == "cancelled":
                        return
                    persisted_review_history.clear()
                    try:
                        reviewed_content, model_name, review_result = await generate_reviewed_content(
                            context, client_factory, content_token_fn,
                            on_review_iteration=persist_review_iteration,
                        )
                    except LLMRequestError as error:
                        if attempt + 1 >= BACKGROUND_GENERATION_ATTEMPTS or not is_retryable_generation_error(error):
                            raise
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break
                if reviewed_content is None:
                    raise ContentQualityError("评审流程未生成可用正文")
                job.output_content = reviewed_content
                job.progress = 95
                await db.commit()
                review_metadata = review_result.metadata() if review_result else {"review_enabled": False}
                await generation_crud.complete_job_if_active(
                    db, job_id, output_content=reviewed_content,
                    result={
                        "expected_words": context.plan.expected_words,
                        "plan": context.plan.model_dump(),
                        "citations": context.citations,
                        "model": model_name,
                        "prompt_template_id": "chapter_content",
                        "prompt_template_version": get_prompt_template("chapter_content").version,
                        "segments": len(build_content_segments(context)),
                        "quality_check": "passed",
                        **review_metadata,
                    },
                )
                return

            def remember_client(client):
                nonlocal model_name
                model_name = client.model

            for attempt in range(BACKGROUND_GENERATION_ATTEMPTS):
                current_status = await db.scalar(
                    select(GenerationJob.status).where(GenerationJob.id == job_id)
                )
                if current_status == "cancelled":
                    return
                parts.clear()
                try:
                    async for chunk in stream_content(
                        context, client_factory, content_token_fn, on_client=remember_client,
                    ):
                        parts.append(chunk)
                        current_status = await db.scalar(
                            select(GenerationJob.status).where(GenerationJob.id == job_id)
                        )
                        if current_status == "cancelled":
                            return
                        job.output_content = "".join(parts)
                        job.progress = min(95, 5 + len(job.output_content) * 90 // max(1, context.plan.expected_words))
                        now = asyncio.get_running_loop().time()
                        if now - last_persisted >= 1:
                            await db.commit()
                            last_persisted = now
                except LLMRequestError as error:
                    if attempt + 1 >= BACKGROUND_GENERATION_ATTEMPTS or not is_retryable_generation_error(error):
                        raise
                    # A streamed response cannot safely resume mid-sentence.
                    # Discard the partial attempt before retrying the whole draft.
                    job.output_content = None
                    job.progress = 5
                    await db.commit()
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                break
            content = "".join(parts).strip()
            validate_content_quality(content, context.plan.expected_words)
            await generation_crud.complete_job_if_active(
                db, job_id, output_content=content,
                result={
                    "expected_words": context.plan.expected_words,
                    "plan": context.plan.model_dump(),
                    "citations": context.citations,
                    "model": model_name,
                    "prompt_template_id": "chapter_content",
                    "prompt_template_version": get_prompt_template("chapter_content").version,
                    "segments": len(build_content_segments(context)),
                    "quality_check": "passed",
                },
            )
    except asyncio.CancelledError:
        # The cancel endpoint owns the persisted terminal state. Re-raise so
        # the task stops immediately instead of being converted to a failure.
        raise
    except LLMConfigurationError:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL")
    except (LLMError, HTTPException) as error:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message=getattr(error, "detail", "章节生成暂时不可用，请稍后重试"))
    except ContentQualityError as error:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message=str(error))
    except Exception:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message="章节生成失败，请稍后重试")
