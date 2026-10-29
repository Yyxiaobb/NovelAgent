"""Durable background generation for chapter summaries and memories."""

from __future__ import annotations

import json
from collections.abc import Callable
from time import perf_counter

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent import LLMConfigurationError, LLMError
from agent.prompts import render_prompt
from config.db_conf import AsyncSessionLocal
from crud import generation as generation_crud
from crud import projects
from crud import story_memory as story_memory_crud
from models.generation import GenerationJob
from models.projects import PROJECT_STATE_TEMPLATE
from schemas.projects import ChapterMemory
from services.agent_generation import memory_max_tokens as _memory_max_tokens
from services.agent_generation import text_value as _text_value
from services.generation_runtime import generation_client
from utils.generation_telemetry import log_generation_metric


def _json_candidate(raw: str):
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(candidate)


async def generate_chapter_memory(
    db: AsyncSession,
    project_id: int,
    chapter_id: int,
    user_id: int,
    user_idea: str | None = None,
    *,
    client_factory: Callable = generation_client,
) -> tuple[str, ChapterMemory]:
    """Generate and persist one chapter's summary and structured memory."""
    project = await projects.get_project(db, project_id, user_id)
    chapter = await projects.get_chapter(db, project_id, chapter_id, user_id)
    if project is None or chapter is None:
        raise HTTPException(status_code=404, detail="作品或章节不存在、已删除或不可访问")
    if not (chapter.content or "").strip():
        raise HTTPException(status_code=422, detail="章节正文为空，无法整理摘要")

    existing_state_markdown = project.current_state_markdown or PROJECT_STATE_TEMPLATE
    context_started = perf_counter()
    memory_template, prompt = render_prompt(
        "chapter_memory",
        project_type=project.project_type or "未指定",
        project_outline=project.outline or "暂未提供",
        current_state_markdown=existing_state_markdown[:16000],
        chapter_number=chapter.chapter_number,
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
        async with client_factory() as client:
            model_started = perf_counter()
            raw = (await client.achat(
                [
                    {"role": "system", "content": memory_template.system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=_memory_max_tokens(chapter.content),
            )).strip()
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
            status_code=503,
            detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
        ) from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail="章节摘要整理暂时不可用，请稍后重试") from error

    try:
        parsed = _json_candidate(raw)
        if not isinstance(parsed, dict):
            raise ValueError("memory must be an object")
        summary = _text_value(parsed.pop("summary"))
        memory = ChapterMemory.model_validate({
            field: _text_value(parsed.get(field, "无"))
            for field in ("character_state", "setting_changes", "unresolved_threads", "timeline")
        })
        project_state_markdown = _text_value(parsed.get("project_state_markdown"))
        if not project_state_markdown or len(project_state_markdown) > 20000:
            raise ValueError("project_state_markdown is empty or too long")
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(status_code=502, detail="模型返回的章节记忆格式无效，请重试") from error

    persist_started = perf_counter()
    chapter.summary = summary
    chapter.memory = memory.model_dump()
    await db.refresh(project, attribute_names=["current_state_markdown"])
    if (project.current_state_markdown or PROJECT_STATE_TEMPLATE) == existing_state_markdown:
        project.current_state_markdown = project_state_markdown
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
    return summary, memory


async def run_chapter_memory_job(
    job_id: str,
    session_factory: async_sessionmaker = AsyncSessionLocal,
    client_factory: Callable = generation_client,
) -> None:
    """Run a queued memory job and persist a durable terminal status."""
    try:
        async with session_factory() as db:
            job = await db.get(GenerationJob, job_id)
            if job is None or job.status == "cancelled" or not await generation_crud.start_job_if_active(db, job_id):
                return
            payload = job.input_payload or {}
            summary, memory = await generate_chapter_memory(
                db,
                job.project_id,
                job.chapter_id,
                job.user_id,
                payload.get("user_idea"),
                client_factory=client_factory,
            )
            await generation_crud.complete_job_if_active(
                db,
                job_id,
                output_content=summary,
                result={"summary": summary, "memory": memory.model_dump()},
            )
    except HTTPException as error:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message=str(error.detail))
    except Exception:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message="章节摘要整理失败，请稍后重试")
