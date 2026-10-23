import html

import re


from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException


from sqlalchemy.ext.asyncio import AsyncSession

from starlette import status

from agent import LLMConfigurationError, LLMError, LLMRequestError

from config.db_conf import get_db


from crud import projects


from models.users import User

from schemas.agent import (
    IdeaRefinementRequest,
    IdeaRefinementResponse,
    OutlineGenerationRequest,
    OutlineGenerationResponse,
    ProjectFieldGenerationRequest,
    ProjectFieldGenerationResponse,
)


from schemas.projects import ProjectInfoBase

from services.knowledge_rag import (
    EmbeddingConfigurationError,
    EmbeddingRequestError,
    format_retrieved_context,
    retrieve_knowledge,
)

from utils.auth import get_current_user

from utils.response import success_response

from utils.generation_telemetry import log_generation_metric

from utils.media import save_svg

from services.agent_generation import (
    PROJECT_TYPES as _PROJECT_TYPES,
    json_candidate as _json_candidate,
    outline_max_tokens as _outline_max_tokens,
)


from agent.prompts import render_prompt


from services.generation_runtime import generation_client

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _cover_color(value: object, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if re.fullmatch(r"#[0-9a-fA-F]{6}", candidate) else fallback


def _cover_svg(*, title: str, subtitle: str, mood: str, primary: str, secondary: str) -> str:
    safe_title = html.escape(title[:18] or "未命名作品")
    safe_subtitle = html.escape(subtitle[:24] or "一场故事，正在发生")
    safe_mood = html.escape(mood[:12] or "小说创作")
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
</svg>'''


def _prompt(payload: ProjectFieldGenerationRequest):
    if payload.field == "projectname":
        instruction = "请生成一个有辨识度、适合小说封面的中文作品名，只返回作品名，不要引号、序号或解释。"
    elif payload.field == "introduction":
        instruction = "请生成一段 80 到 180 字的中文小说简介，包含主角、背景和核心冲突，只返回简介正文。"
    else:
        instruction = f"请从以下类型中选择最合适的一项，只返回类型名称：{_PROJECT_TYPES}。"
    return render_prompt(
        "project_field",
        project_name=payload.projectname or "未填写",
        project_introduction=payload.introduction or "未填写",
        project_type=payload.project_type or "未选择",
        instruction=instruction,
    )


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
        async with generation_client(timeout=90) as client:
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
            detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
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


@router.post("/project-field", response_model=None)
async def generate_project_field(
    payload: ProjectFieldGenerationRequest,
    _: User = Depends(get_current_user),
):
    template, prompt = _prompt(payload)
    try:
        async with generation_client() as client:
            model_started = perf_counter()
            value = (
                await client.achat(
                    [
                        {"role": "system", "content": template.system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
            ).strip()
            log_generation_metric(
                "model_complete",
                f"project_field:{payload.field}",
                (perf_counter() - model_started) * 1000,
                prompt_chars=len(prompt),
                output_chars=len(value),
                model=client.model,
            )
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


@router.post("/projects/{project_id}/cover", response_model=None)
async def generate_project_cover(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    template, prompt = render_prompt(
        "project_cover",
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        project_outline=(project.outline or "未提供")[:12000],
    )
    try:
        async with generation_client(timeout=60) as client:
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
            detail="智能封面生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL",
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

    template, prompt = render_prompt(
        "project_outline",
        project_name=project.projectname or "未命名作品",
        project_type=project.project_type or "未指定",
        project_introduction=project.introduction or "未提供",
        user_idea=payload.user_idea.strip() if payload.user_idea and payload.user_idea.strip() else "未提供",
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
                        project.projectname or "",
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
        async with generation_client(timeout=120) as client:
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
            citations=citations,
        ),
    )
