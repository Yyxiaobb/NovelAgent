import asyncio
import json
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent import LLMConfigurationError, LLMError
from crud import generation as generation_crud
from crud import projects
from crud import story_memory as story_memory_crud
from models.generation import GenerationJob
from schemas.agent import ChapterGenerationRequest
from schemas.projects import ChapterPlan
from services.story_memory import build_project_memory_context, build_story_memory


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
    prompt = (
        "你是一名专业的中文小说作者，请依据作品设定创作指定章节正文。\n"
        f"作品名称：{project.projectname or '未命名作品'}\n作品类型：{project.project_type or '未指定'}\n"
        f"作品简介：{project.introduction or '未提供'}\n作品大纲：{project.outline or '暂未提供，请依据简介自然展开'}\n"
        f"前文章节记忆（最近 5 章）：\n{prior_context}\n\n历史章节记忆：\n{story_memory}\n"
        f"作品长期记忆（根据本章规划检索）：\n{project_memory_context}\n"
        f"章节规划：{plan.model_dump()}\n"
        f"用户补充想法：{payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else '未提供'}\n"
        f"章节编号：第 {chapter.chapter_number} 章\n章节名称：{chapter.chaptername or '未命名章节'}\n"
        f"期望本章字数：约 {plan.expected_words} 字\n\n"
        f"本章必须完成的目标：{plan.objective}\n本章核心冲突：{plan.conflict}\n"
        f"关键情节：{plan.key_events}\n结尾钩子：{plan.ending_hook}\n\n"
        "要求：承接大纲及前文设定，保持人物性格和叙事视角一致；只输出小说正文，不要输出标题、写作说明或字数统计。"
    )
    return project, chapter, plan, prompt


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
            project, chapter, plan, prompt = await build_context(db, job.project_id, job.chapter_id, job.user_id, payload)
            parts: list[str] = []
            last_persisted = asyncio.get_running_loop().time()
            async with client_factory() as client:
                async for chunk in client.astream([
                    {"role": "system", "content": "你输出的内容将作为小说章节草稿，只输出正文。"},
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
                result={"expected_words": plan.expected_words, "plan": plan.model_dump()},
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
