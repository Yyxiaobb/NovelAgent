from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from crud import story_memory as memory_crud
from crud import projects
from models.users import User
from schemas.story_memory import StoryMemoryInfo, StoryMemoryRequest
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
