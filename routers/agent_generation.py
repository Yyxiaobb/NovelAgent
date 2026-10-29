import html
import json

import re


from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select

from starlette import status

from agent import LLMConfigurationError, LLMError, LLMRequestError

from config.db_conf import get_db


from crud import inspirations, projects


from models.users import User
from models.outline_volume import OutlineVolume
from crud import outline_volume_versions

from schemas.agent import (
    IdeaRefinementRequest,
    IdeaRefinementResponse,
    OutlineGenerationRequest,
    OutlineGenerationResponse,
    OutlineVolumeGenerationRequest,
    OutlineVolumePlanGenerationRequest,
    OutlineVolumePlanItem,
    ProjectCoverGenerationRequest,
)


from schemas.projects import OutlineVolumeInfo, ProjectInfoBase

from services.knowledge_rag import (
    EmbeddingConfigurationError,
    EmbeddingRequestError,
    format_retrieved_context,
    retrieve_knowledge,
)
from services.inspiration_context import format_inspiration_context

from utils.auth import get_current_user

from utils.response import success_response

from utils.generation_telemetry import log_generation_metric

from utils.media import save_svg

from services.agent_generation import (
    json_candidate as _json_candidate,
    outline_max_tokens as _outline_max_tokens,
)


from agent.prompts import render_prompt


from services.generation_runtime import generation_client
from services.chapter_generation import sse

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _cover_color(value: object, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate) else fallback


def _cover_svg(*, title: str, subtitle: str, mood: str, author_name: str, primary: str, secondary: str) -> str:
    safe_title = html.escape(title[:18] or "未命名作品")
    safe_subtitle = html.escape(subtitle[:24] or "一场故事，正在发生")
    safe_mood = html.escape(mood[:12] or "小说创作")
    safe_author = html.escape(author_name[:50] or "未署名")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="760" height="1080" viewBox="0 0 760 1080">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{primary}"/><stop offset="1" stop-color="{secondary}"/></linearGradient>
    <radialGradient id="glow" cx="78%" cy="18%" r="70%"><stop offset="0" stop-color="#ffffff" stop-opacity=".32"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="28"/></filter>
  </defs>
  <rect width="760" height="1080" fill="url(#bg)"/>
  <rect width="760" height="1080" fill="url(#glow)"/>
  <circle cx="610" cy="160" r="180" fill="#ffffff" opacity=".10" filter="url(#blur)"/>
  <path d="M0 820 C180 700 290 920 470 780 S650 690 760 760 V1080 H0Z" fill="#060b18" opacity=".42"/>
  <path d="M80 140 H680" stroke="#ffffff" stroke-opacity=".55"/>
  <text x="80" y="205" fill="#ffffff" fill-opacity=".78" font-family="Microsoft YaHei, sans-serif" font-size="20" letter-spacing="7">{safe_mood}</text>
  <text x="80" y="650" fill="#ffffff" font-family="Microsoft YaHei, sans-serif" font-size="64" font-weight="700">{safe_title}</text>
  <text x="80" y="705" fill="#ffffff" fill-opacity=".82" font-family="Microsoft YaHei, sans-serif" font-size="22">{safe_subtitle}</text>
  <rect x="80" y="790" width="100" height="4" fill="#ffffff" fill-opacity=".7"/>
  <text x="80" y="850" fill="#ffffff" fill-opacity=".68" font-family="Microsoft YaHei, sans-serif" font-size="16" letter-spacing="4">墨笺 · NOVEL WORKSPACE</text>
  <text x="80" y="930" fill="#ffffff" fill-opacity=".82" font-family="Microsoft YaHei, sans-serif" font-size="22">作者：{safe_author}</text>
</svg>'''


@router.post("/refine-idea", response_model=None)
async def refine_idea(
    payload: IdeaRefinementRequest,
    _: User = Depends(get_current_user),
):
    idea = payload.idea.strip()
    if not idea:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="灵感内容不能为空")
    template, prompt = render_prompt("idea_refinement", idea=idea)
    try:
        async with generation_client(timeout=300) as client:
            model_started = perf_counter()
            refined = (
                await client.achat(
                    [
                        {"role": "system", "content": template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=1800,
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                "idea_refinement",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(refined),
                model=client.model,
                max_tokens=1800,
            )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
        ) from error
    except LLMRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="创意完善响应超时，请缩短灵感内容后重试",
        ) from error
    except LLMError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="创意完善暂时不可用，请稍后重试") from error
    if not refined:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="模型未返回可用的完善结果")
    return success_response(
        message="创意完善成功",
        data=IdeaRefinementResponse(idea=idea, refined_idea=refined),
    )


@router.post("/projects/{project_id}/cover", response_model=None)
async def generate_project_cover(
    project_id: int,
    payload: ProjectCoverGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    author_name = payload.author_name.strip()
    if not author_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="作者名不能为空")
    template, prompt = render_prompt(
        "project_cover",
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        project_outline=(project.outline or "未提供")[:12000],
        author_name=author_name,
    )
    try:
        async with generation_client(timeout=300) as client:
            model_started = perf_counter()
            raw = (
                await client.achat(
                    [
                        {"role": "system", "content": template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=400,
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                "project_cover",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(raw),
                model=client.model,
                max_tokens=400,
            )
        try:
            parsed_design = _json_candidate(raw)
            design = parsed_design if isinstance(parsed_design, dict) else {}
        except (TypeError, ValueError, KeyError):
            design = {}
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能封面生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
        ) from error
    except LLMRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="智能封面生成响应超时，请稍后重试"
        ) from error
    except LLMError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="智能封面生成暂时不可用，请稍后重试"
        ) from error

    svg = _cover_svg(
        title=str(design.get("title") or project.projectname or "未命名作品"),
        subtitle=str(design.get("subtitle") or project.project_type or "一场故事，正在发生"),
        mood=str(design.get("mood") or "小说创作"),
        author_name=author_name,
        primary=_cover_color(design.get("primary_color"), "#102a43"),
        secondary=_cover_color(design.get("secondary_color"), "#3b4a86"),
    )
    project.cover_url = save_svg(svg)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return success_response(message="智能封面生成成功", data=ProjectInfoBase.model_validate(project))


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
        selected_inspirations = await inspirations.get_inspirations_for_generation(
            db, user.id, payload.inspiration_ids
        )
    except PermissionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    template, prompt = render_prompt(
        "project_outline",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
        inspiration_context=format_inspiration_context(selected_inspirations),
        expected_words=payload.expected_words,
    )
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
                        project.introduction or "",
                        payload.user_idea or "",
                        f"目标字数 {payload.expected_words}",
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
    try:
        async with generation_client(timeout=300) as client:
            model_started = perf_counter()
            outline = (
                await client.achat(
                    [
                        {"role": "system", "content": template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.5,
                    max_tokens=_outline_max_tokens(payload.expected_words),
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                "project_outline",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(outline),
                model=client.model,
                max_tokens=_outline_max_tokens(payload.expected_words),
            )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL",
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
            citations=citations,
        ),
    )


@router.post("/projects/{project_id}/outline/stream", response_model=None)
async def generate_project_outline_stream(
    project_id: int,
    payload: OutlineGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")

    try:
        selected_inspirations = await inspirations.get_inspirations_for_generation(
            db, user.id, payload.inspiration_ids
        )
    except PermissionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    template, prompt = render_prompt(
        "project_outline",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
        inspiration_context=format_inspiration_context(selected_inspirations),
        expected_words=payload.expected_words,
    )
    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db,
                user_id=user.id,
                knowledge_base_ids=payload.knowledge_base_ids,
                query="\n".join((
                    project.project_type or "",
                    project.introduction or "",
                    payload.user_idea or "",
                    f"目标字数 {payload.expected_words}",
                )),
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

    async def events():
        started = perf_counter()
        first_chunk_ms = None
        parts: list[str] = []
        try:
            async with generation_client(timeout=300) as client:
                async for chunk in client.astream(
                    [
                        {"role": "system", "content": template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.5,
                    max_tokens=_outline_max_tokens(payload.expected_words),
                ):
                    if first_chunk_ms is None:
                        first_chunk_ms = (perf_counter() - started) * 1000
                    parts.append(chunk)
                    yield sse("chunk", chunk)
                outline = "".join(parts).strip()
                if not outline:
                    yield sse("error", "模型未返回可用大纲")
                    return
                project.expected_words = payload.expected_words
                await db.commit()
                log_generation_metric(
                    "model_stream_complete",
                    "project_outline",
                    (perf_counter() - started) * 1000,
                    first_chunk_ms=round(first_chunk_ms, 2) if first_chunk_ms is not None else None,
                    prompt_chars=len(prompt),
                    output_chars=len(outline),
                    model=client.model,
                    max_tokens=_outline_max_tokens(payload.expected_words),
                )
                yield sse("done", {"project_id": project.id, "expected_words": payload.expected_words, "citations": citations})
        except LLMConfigurationError:
            yield sse("error", "智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL")
        except LLMRequestError:
            yield sse("error", "大纲生成响应超时，请稍后重试或减少补充想法")
        except LLMError:
            yield sse("error", "大纲生成暂时不可用，请稍后重试")

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/projects/{project_id}/outline/volumes/generate-plan")
async def generate_outline_volume_plan(
    project_id: int,
    payload: OutlineVolumePlanGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="作品不存在或已在回收站")
    if not (project.outline or "").strip():
        raise HTTPException(status_code=422, detail="请先填写并保存全书总纲，再进行智能分卷")

    existing_volumes = await projects.get_outline_volumes(db, project_id)
    if existing_volumes and not payload.replace_existing:
        raise HTTPException(status_code=409, detail="已有卷纲；确认替换后才能重新智能分卷")

    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db,
                user_id=user.id,
                knowledge_base_ids=payload.knowledge_base_ids,
                query=f"{project.project_type or ''}\n{project.outline[:5000]}\n{payload.user_idea or ''}",
            )
        except PermissionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except EmbeddingConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EmbeddingRequestError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    planner_template, planner_prompt = render_prompt(
        "outline_volume_planner",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        expected_words=payload.expected_words,
        project_outline=project.outline[:20000],
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "无",
    )
    reference_context = format_retrieved_context(citations) or "无"
    planner_prompt += reference_context
    phase = "分卷规划"
    try:
        async with generation_client(timeout=300) as client:
            stage_started = perf_counter()
            raw_plan = await client.achat(
                [
                    {"role": "system", "content": planner_template.system},
                    {"role": "user", "content": planner_prompt},
                ],
                temperature=0.5,
                max_tokens=5000,
            )
            log_generation_metric(
                "model_complete",
                "outline_volume_planner",
                (perf_counter() - stage_started) * 1000,
                prompt_chars=len(planner_prompt),
                output_chars=len(raw_plan),
                model=client.model,
                max_tokens=5000,
            )
            try:
                parsed = _json_candidate(raw_plan)
                raw_items = parsed.get("volumes") if isinstance(parsed, dict) else None
                if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 30:
                    raise ValueError("volumes must contain 1 to 30 items")
                items = [OutlineVolumePlanItem.model_validate(item) for item in raw_items]
            except (TypeError, ValueError) as error:
                raise HTTPException(status_code=502, detail="模型返回的分卷计划格式无效，请重试") from error

            executor_items = [
                {key: value for key, value in item.model_dump().items() if key != "name"}
                for item in items
            ]
            full_plan = json.dumps(executor_items, ensure_ascii=False)

            generated_outlines: list[str] = []
            for index, item in enumerate(items, start=1):
                phase = f"第{index}卷卷纲执行"
                executor_template, executor_prompt = render_prompt(
                    "outline_volume_executor",
                    project_type=project.project_type or "未指定",
                    project_introduction=project.introduction or "未提供",
                    expected_words=payload.expected_words,
                    project_outline=project.outline[:20000],
                    volume_plan=full_plan,
                    current_volume=json.dumps(
                        {key: value for key, value in item.model_dump().items() if key != "name"},
                        ensure_ascii=False,
                    ),
                    previous_volumes=(
                        "\n\n".join(
                            f"第{previous_index}卷已生成卷纲：\n{outline[:1800]}"
                            for previous_index, outline in enumerate(generated_outlines[-2:], start=max(1, index - 2))
                        )
                        or "当前为第一卷"
                    ),
                    reference_context=reference_context,
                )
                stage_started = perf_counter()
                outline = (
                    await client.achat(
                        [
                            {"role": "system", "content": executor_template.system},
                            {"role": "user", "content": executor_prompt},
                        ],
                        temperature=0.5,
                        max_tokens=3500,
                    )
                ).strip()
                log_generation_metric(
                    "model_complete",
                    "outline_volume_executor",
                    (perf_counter() - stage_started) * 1000,
                    volume_number=index,
                    prompt_chars=len(executor_prompt),
                    output_chars=len(outline),
                    model=client.model,
                    max_tokens=3500,
                )
                if len(outline) < 80:
                    raise HTTPException(status_code=502, detail=f"{phase}返回内容过短，请重试")
                generated_outlines.append(outline)
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail="智能分卷尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL") from error
    except LLMRequestError as error:
        raise HTTPException(status_code=504, detail=f"{phase}响应超时，请稍后重试") from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail=f"{phase}失败，请稍后重试") from error

    new_volumes = []
    for index, (item, outline) in enumerate(zip(items, generated_outlines), start=1):
        new_volumes.append(
            OutlineVolume(
                project_id=project.id,
                volume_number=index,
                name=item.name,
                outline=outline,
            )
        )

    if existing_volumes:
        for existing_volume in existing_volumes:
            await outline_volume_versions.add_snapshot(db, existing_volume, user.id, source="before_regenerate")
        await db.execute(delete(OutlineVolume).where(
            OutlineVolume.project_id == project.id, OutlineVolume.is_deleted.is_(False)
        ))
    # Recycled volume numbers remain reserved by the existing unique constraint.
    recycled_numbers = set((await db.scalars(select(OutlineVolume.volume_number).where(
        OutlineVolume.project_id == project.id, OutlineVolume.is_deleted.is_(True)
    ))).all())
    available_numbers = (number for number in range(1, len(items) + len(recycled_numbers) + 1) if number not in recycled_numbers)
    for volume, number in zip(new_volumes, available_numbers):
        volume.volume_number = number
    db.add_all(new_volumes)
    await db.commit()
    saved_volumes = await projects.get_outline_volumes(db, project.id)
    return success_response(
        message="智能分卷成功",
        data={
            "project_id": project.id,
            "expected_words": payload.expected_words,
            "volumes": [OutlineVolumeInfo.model_validate(volume) for volume in saved_volumes],
            "citations": citations,
        },
    )


@router.post("/projects/{project_id}/outline/volumes/{volume_id}/generate")
async def generate_outline_volume(
    project_id: int,
    volume_id: int,
    payload: OutlineVolumeGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="作品不存在或已在回收站")
    volume = await db.scalar(
        select(OutlineVolume).where(OutlineVolume.project_id == project_id, OutlineVolume.id == volume_id)
    )
    if volume is None:
        raise HTTPException(status_code=404, detail="卷纲不存在")
    # The current volume is the source of truth. Generation never asks the
    # user to re-enter the work or volume metadata.
    previous_outline = volume.outline
    previous_volume = await db.scalar(select(OutlineVolume).where(
        OutlineVolume.project_id == project_id,
        OutlineVolume.is_deleted.is_(False),
        OutlineVolume.volume_number < volume.volume_number,
    ).order_by(OutlineVolume.volume_number.desc(), OutlineVolume.id.desc()))
    previous_volume_context = (
        f"{(previous_volume.outline or '上一卷尚未填写卷纲')[:10000]}"
        if previous_volume is not None
        else "当前为第一卷，没有上一卷卷纲。"
    )

    citations = []
    if payload.knowledge_base_ids:
        try:
            citations = await retrieve_knowledge(
                db,
                user_id=user.id,
                knowledge_base_ids=payload.knowledge_base_ids,
                query=f"{project.project_type or ''}\n{previous_outline or ''}\n{payload.user_idea or ''}",
            )
        except PermissionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except EmbeddingConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EmbeddingRequestError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    prompt = (
        f"请根据作品设定编写第{volume.volume_number}卷的卷纲。\n"
        f"类型：{project.project_type or '未指定'}\n简介：{project.introduction or '未提供'}\n"
        f"全书总纲：\n{(project.outline or '未提供')[:10000]}\n"
        f"上一卷卷纲（用于承接情节）：\n{previous_volume_context}\n"
        "本卷推进没有预设字数或章节范围；按卷纲中的阶段目标和事件因果展开。\n"
        f"本卷已有规划（如有）：\n{(previous_outline or '尚未填写')[:8000]}\n"
        f"补充想法：{payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else '无'}\n\n"
        "请写出本卷阶段目标、核心冲突、关键事件顺序、主要人物状态变化、伏笔及回收、卷末高潮和后续钩子。"
        "卷纲要细于全书总纲、粗于单章细纲，不要写小说正文，也不要拆成逐章细纲。只输出中文卷纲。"
    )
    prompt += format_retrieved_context(citations)
    try:
        async with generation_client(timeout=300) as client:
            outline = (await client.achat(
                [{"role": "system", "content": "你是长篇小说分卷策划编辑，确保卷纲严格承接全书总纲。"},
                 {"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=5000,
            )).strip()
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail="智能生成尚未配置模型，请先配置 MODEL、API_KEY 和 BASE_URL") from error
    except LLMRequestError as error:
        raise HTTPException(status_code=504, detail="卷纲生成响应超时，请稍后重试") from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail="卷纲生成暂时不可用，请稍后重试") from error
    if not outline:
        raise HTTPException(status_code=502, detail="模型未返回可用卷纲")
    return success_response(message="卷纲生成成功", data={"project_id": project.id, "volume_id": volume.id, "outline": outline, "citations": citations})
