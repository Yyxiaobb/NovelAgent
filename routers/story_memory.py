from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from crud import story_memory as memory_crud
from crud import projects
from models.users import User
from schemas.story_memory import (
    StoryMemoryBatchReviewRequest,
    StoryMemoryConflictInfo,
    StoryMemoryEventInfo,
    StoryMemoryInfo,
    StoryMemoryMergeRequest,
    StoryMemoryRequest,
    StoryMemoryReviewRequest,
)
from services.story_memory import find_memory_conflicts
from utils.auth import get_current_user
from utils.response import success_response


router = APIRouter(prefix="/api/project/{project_id}/memories", tags=["story memory"])


@router.get("")
async def list_memories(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memories = await memory_crud.list_project_memories(db, project_id, user.id)
    if memories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    return success_response(message="获取长期记忆成功", data=[StoryMemoryInfo.model_validate(item) for item in memories])


@router.get("/conflicts")
async def list_memory_conflicts(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memories = await memory_crud.list_project_memories(db, project_id, user.id)
    if memories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    conflicts = find_memory_conflicts(memories)
    return success_response(
        message="获取记忆冲突提示成功",
        data=[StoryMemoryConflictInfo.model_validate(item) for item in conflicts],
    )


@router.get("/events")
async def list_memory_events(
    project_id: int = Path(..., gt=0),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    events = await memory_crud.list_project_memory_events(db, project_id, user.id, limit=limit)
    if events is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    return success_response(message="获取记忆操作记录成功", data=[StoryMemoryEventInfo.model_validate(item) for item in events])


@router.post("")
async def create_memory(
    payload: StoryMemoryRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if await projects.get_project(db, project_id, user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    if payload.source_chapter_id is not None and await projects.get_chapter(
        db, project_id, payload.source_chapter_id, user.id,
    ) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="来源章节不存在或不属于该作品")
    memory = await memory_crud.create_project_memory(db, project_id, user.id, payload)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    return success_response(message="长期记忆已添加", data=StoryMemoryInfo.model_validate(memory))


@router.put("/{memory_id}")
async def update_memory(
    payload: StoryMemoryRequest,
    project_id: int = Path(..., gt=0),
    memory_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memory = await memory_crud.get_project_memory(db, project_id, memory_id, user.id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="长期记忆不存在或不可访问")
    if payload.source_chapter_id is not None and await projects.get_chapter(
        db, project_id, payload.source_chapter_id, user.id,
    ) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="来源章节不存在或不属于该作品")
    updated = await memory_crud.update_project_memory(db, memory, payload)
    return success_response(message="长期记忆已更新", data=StoryMemoryInfo.model_validate(updated))


@router.delete("/{memory_id}")
async def remove_memory(
    project_id: int = Path(..., gt=0),
    memory_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memory = await memory_crud.get_project_memory(db, project_id, memory_id, user.id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="长期记忆不存在或不可访问")
    await memory_crud.delete_project_memory(db, memory)
    return success_response(message="长期记忆已删除", data={"id": memory_id})


@router.post("/{memory_id}/review")
async def review_memory(
    payload: StoryMemoryReviewRequest,
    project_id: int = Path(..., gt=0),
    memory_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memory = await memory_crud.get_project_memory(db, project_id, memory_id, user.id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="长期记忆不存在或不可访问")
    if memory.origin != "chapter_extract" or memory.review_status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有待审核的章节提取记忆可以审核")
    reviewed = await memory_crud.review_project_memory(db, memory, payload.decision, actor_user_id=user.id)
    return success_response(message="长期记忆审核完成", data=StoryMemoryInfo.model_validate(reviewed))


@router.post("/batch-review")
async def batch_review_memories(
    payload: StoryMemoryBatchReviewRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memories = await memory_crud.list_project_memories(db, project_id, user.id)
    if memories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    selected = [item for item in memories if item.id in set(payload.memory_ids)]
    if len(selected) != len(set(payload.memory_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分长期记忆不存在或不可访问")
    if any(item.origin != "chapter_extract" or item.review_status != "pending" for item in selected):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="批量审核只支持待审核的章节提取记忆")
    reviewed = await memory_crud.review_project_memories(db, selected, payload.decision, actor_user_id=user.id)
    return success_response(
        message="长期记忆批量审核完成",
        data=[StoryMemoryInfo.model_validate(item) for item in reviewed],
    )


@router.post("/merge")
async def merge_memories(
    payload: StoryMemoryMergeRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memories = await memory_crud.list_project_memories(db, project_id, user.id)
    if memories is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或不可访问")
    source_ids = list(dict.fromkeys(payload.source_ids))
    if payload.target_id in source_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="合并目标不能同时作为来源条目")
    by_id = {memory.id: memory for memory in memories}
    if payload.target_id not in by_id or any(memory_id not in by_id for memory_id in source_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分长期记忆不存在或不可访问")
    target = by_id[payload.target_id]
    sources = [by_id[memory_id] for memory_id in source_ids]
    if any(memory.category != target.category for memory in sources):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能合并同一类型的长期记忆")
    if any(memory.merged_into_id is not None for memory in [target, *sources]):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已合并的记忆不能再次作为合并对象")
    merged, _ = await memory_crud.merge_project_memories(
        db, project_id=project_id, actor_user_id=user.id, target=target, sources=sources,
    )
    return success_response(message="长期记忆已合并", data=StoryMemoryInfo.model_validate(merged))
