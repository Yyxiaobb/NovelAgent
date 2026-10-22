import asyncio
import json
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent import LLMConfigurationError, LLMError
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


async def build_context(db: AsyncSession, project_id: int, chapter_id: int, user_id: int, payload: ChapterGenerationRequest):
    project = await projects.get_project(db, project_id, user_id)
    chapter = await projects.get_chapter(db, project_id, chapter_id, user_id)
    if project is None or chapter is None:
        raise HTTPException(status_code=404, detail="作品或章节不存在、已删除或不可访问")
    plan = payload.plan or (ChapterPlan.model_validate(chapter.plan) if chapter.plan else ChapterPlan(
        objective="推进本章故事并完成章节目标", conflict="主角面对当前情节中的核心阻碍",
        key_events="围绕作品大纲展开本章关键事件", ending_hook="留下推动下一章的悬念",
        expected_words=payload.expected_words or 3000,
    ))
    prior_chapters = await projects.get_prior_chapter_memories(db, project.id, chapter.chapter_number)
    memory_chapters = await projects.get_story_memory_chapters(db, project.id, chapter.chapter_number)
    prior_context = "\n".join(
        f"第 {item.chapter_number} 章《{item.chaptername or '未命名'}》摘要：{item.summary}\n"
        f"人物状态：{(item.memory or {}).get('character_state', '未记录')}\n"
        f"未解决线索：{(item.memory or {}).get('unresolved_threads', '未记录')}"
        for item in prior_chapters if item.summary
    ) or "暂无已整理的前文摘要"
    story_memory = build_story_memory(memory_chapters)
    project_memories = await story_memory_crud.list_active_project_memories(db, project.id)
    memory_query = "\n".join((
        chapter.chaptername or "", plan.objective, plan.conflict, plan.key_events,
        plan.ending_hook, payload.user_idea or "",
    ))
    project_memory_context = build_project_memory_context(
        project_memories, memory_query, current_chapter_id=chapter.id,
    )
    _, prompt = render_prompt(
        "chapter_content",
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        project_outline=project.outline or "暂未提供，请依据简介自然展开",
        prior_context=prior_context,
        story_memory=story_memory,
        project_memory_context=project_memory_context,
        plan=plan.model_dump(),
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
        chapter_number=chapter.chapter_number,
        chapter_name=chapter.chaptername or "未命名章节",
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
                query="\n".join((project.projectname or "", project.project_type or "", chapter.chaptername or "",
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
    return project, chapter, plan, prompt, citations


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
            project, chapter, plan, prompt, citations = await build_context(
                db, job.project_id, job.chapter_id, job.user_id, payload,
            )
            parts: list[str] = []
            last_persisted = asyncio.get_running_loop().time()
            async with client_factory() as client:
                async for chunk in client.astream([
                    {"role": "system", "content": get_prompt_template("chapter_content").system},
                    {"role": "user", "content": prompt},
                ], temperature=0.8, max_tokens=content_token_fn(plan.expected_words)):
                    parts.append(chunk)
                    current_status = await db.scalar(
                        select(GenerationJob.status).where(GenerationJob.id == job_id)
                    )
                    if current_status == "cancelled":
                        return
                    job.output_content = "".join(parts)
                    job.progress = min(95, 5 + len(job.output_content) * 90 // max(1, plan.expected_words))
                    now = asyncio.get_running_loop().time()
                    if now - last_persisted >= 1:
                        await db.commit()
                        last_persisted = now
            await generation_crud.complete_job_if_active(
                db, job_id, output_content="".join(parts),
                result={"expected_words": plan.expected_words, "plan": plan.model_dump(), "citations": citations},
            )
    except asyncio.CancelledError:
        # The cancel endpoint owns the persisted terminal state. Re-raise so
        # the task stops immediately instead of being converted to a failure.
        raise
    except LLMConfigurationError:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL")
    except (LLMError, HTTPException) as error:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message=getattr(error, "detail", "章节生成暂时不可用，请稍后重试"))
    except Exception:
        async with session_factory() as db:
            if job := await db.get(GenerationJob, job_id):
                await generation_crud.update_job(db, job, status="failed", error_message="章节生成失败，请稍后重试")
