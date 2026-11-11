from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from starlette import status

from agent import LLMConfigurationError, LLMError

from config.db_conf import get_db


from crud import review_preferences as review_preferences_crud

from models.users import User

from schemas.agent import (
    ChapterGenerationRequest,
    ChapterGenerationResponse,
)

from utils.auth import get_current_user

from utils.response import success_response

from utils.generation_telemetry import log_generation_metric


from services.agent_generation import (
    content_max_tokens as _content_max_tokens,
)

from services.chapter_generation import (
    ContentQualityError,
    prepare_content_context,
    generate_reviewed_content,
    review_enabled,
    stream_content,
    sse,
    validate_content_quality,
)
from services.generation_runtime import generation_client
from agent import runtime as _agent_runtime
from routers.chapter_review import _persist_manual_review_session, review_router
from routers.chapter_jobs import chapter_jobs_router
from routers.chapter_planning import chapter_planning_router

run_agent = _agent_runtime.run_agent

router = APIRouter(prefix="/api/agent", tags=["agent"])
router.include_router(review_router)
router.include_router(chapter_jobs_router)
router.include_router(chapter_planning_router)

@router.post("/projects/{project_id}/chapters/{chapter_id}/content", response_model=None)
async def generate_chapter_content(
    project_id: int,
    chapter_id: int,
    payload: ChapterGenerationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload.review_preferences = await review_preferences_crud.resolve_preferences(db, user.id, project_id)
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
            review_preferences=payload.review_preferences,
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
    review_session_id = await _persist_manual_review_session(
        db,
        user_id=user.id,
        context=context,
        payload=payload,
        content=content,
        review_result=review_result,
    )
    return success_response(
        message="章节生成成功",
        data=ChapterGenerationResponse(
            project_id=project.id,
            chapter_id=chapter.id,
            expected_words=plan.expected_words,
            plan=plan,
            content=content,
            citations=citations,
            review_session_id=review_session_id,
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
    payload.review_preferences = await review_preferences_crud.resolve_preferences(db, user.id, project_id)
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
            if review_enabled(payload.review_preferences):
                reviewed_content, reviewed_model, review_result = await generate_reviewed_content(
                    context, generation_client, _content_max_tokens,
                    review_preferences=payload.review_preferences,
                )
                client_model = reviewed_model
                generated_parts.append(reviewed_content)
                total = len(reviewed_content)
                yield sse("chunk", reviewed_content)
                review_session_id = await _persist_manual_review_session(
                    db,
                    user_id=user.id,
                    context=context,
                    payload=payload,
                    content=reviewed_content,
                    review_result=review_result,
                )
                review_metadata = review_result.metadata() if review_result else {}
                yield sse(
                    "done",
                    {
                        "project_id": project.id,
                        "chapter_id": chapter.id,
                        "expected_words": plan.expected_words,
                        "plan": plan.model_dump(),
                        "citations": citations,
                        "review_session_id": review_session_id,
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
