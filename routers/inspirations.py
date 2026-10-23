from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent import LLMClient, LLMConfigurationError, LLMError, LLMRequestError
from agent.prompts import render_prompt
from config.db_conf import get_db
from crud import inspirations
from models.users import User
from schemas.inspiration import InspirationCreate, InspirationInfo, InspirationRefineResponse, InspirationUpdate
from utils.auth import get_current_user
from utils.generation_telemetry import log_generation_metric
from utils.response import success_response


router = APIRouter(prefix="/api/inspirations", tags=["inspirations"])


def _item_or_404(item):
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="灵感不存在或已在回收站")
    return item


@router.get("")
async def list_inspirations(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    items = await inspirations.list_inspirations(db, user.id)
    return success_response(message="获取灵感成功", data=[InspirationInfo.model_validate(item) for item in items])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_inspiration(
    payload: InspirationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    title, content = payload.title.strip(), payload.content.strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="灵感标题和内容不能为空")
    item = await inspirations.create_inspiration(db, user.id, title=title, content=content)
    return success_response(message="灵感已保存", data=InspirationInfo.model_validate(item), http_status=201)


@router.get("/{inspiration_id}")
async def get_inspiration(
    inspiration_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _item_or_404(await inspirations.get_inspiration(db, inspiration_id, user.id))
    return success_response(message="获取灵感成功", data=InspirationInfo.model_validate(item))


@router.put("/{inspiration_id}")
async def update_inspiration(
    payload: InspirationUpdate,
    inspiration_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _item_or_404(await inspirations.get_inspiration(db, inspiration_id, user.id))
    title, content = payload.title.strip(), payload.content.strip()
    if not title or not content:
        raise HTTPException(status_code=422, detail="灵感标题和内容不能为空")
    item = await inspirations.update_inspiration(
        db, item, title=title, content=content,
        refined_content=payload.refined_content.strip() if payload.refined_content else None,
    )
    return success_response(message="灵感已保存", data=InspirationInfo.model_validate(item))


@router.post("/{inspiration_id}/refine")
async def refine_inspiration(
    inspiration_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _item_or_404(await inspirations.get_inspiration(db, inspiration_id, user.id))
    template, prompt = render_prompt("idea_refinement", idea=item.content)
    try:
        async with LLMClient(max_retries=0, timeout=90) as client:
            started = perf_counter()
            refined = (await client.achat([
                {"role": "system", "content": template.system},
                {"role": "user", "content": prompt},
            ], temperature=0.7, max_tokens=1800)).strip()
            log_generation_metric(
                "model_complete", "idea_refinement", (perf_counter() - started) * 1000,
                prompt_chars=len(prompt), output_chars=len(refined), model=client.model, max_tokens=1800,
            )
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail="智能生成尚未配置模型，请先配置 LLM_MODEL、LLM_API_KEY 和 LLM_BASE_URL") from error
    except LLMRequestError as error:
        raise HTTPException(status_code=504, detail="创意完善响应超时，请稍后重试") from error
    except LLMError as error:
        raise HTTPException(status_code=502, detail="创意完善暂时不可用，请稍后重试") from error
    if not refined:
        raise HTTPException(status_code=502, detail="模型未返回可用的完善结果")
    item.refined_content = refined
    await db.commit()
    await db.refresh(item)
    return success_response(message="创意完善成功", data=InspirationRefineResponse.model_validate(item))


@router.delete("/{inspiration_id}")
async def delete_inspiration(
    inspiration_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = _item_or_404(await inspirations.get_inspiration(db, inspiration_id, user.id))
    await inspirations.move_to_recycle_bin(db, item)
    return success_response(message="灵感已移入回收站", data={"id": inspiration_id, "is_deleted": True})
