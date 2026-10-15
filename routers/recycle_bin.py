from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from config.db_conf import get_db
from crud import recycle_bin
from models.users import User
from schemas.projects import ChapterInfo, ProjectInfoBase, RecycledChapterInfo
from utils.auth import get_current_user
from utils.response import success_response


router = APIRouter(prefix="/api/recycle-bin", tags=["recycle-bin"])
legacy_router = APIRouter(prefix="/api/project", tags=["projects"], deprecated=True)


async def _move_project(project_id: int, db: AsyncSession, user: User):
    project = await recycle_bin.move_project_to_recycle_bin(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="项目已移入回收站", data=ProjectInfoBase.model_validate(project))


async def _list_projects(db: AsyncSession, user: User):
    project_list = await recycle_bin.get_recycled_projects(db, user.id)
    response = [ProjectInfoBase.model_validate(project) for project in project_list]
    return success_response(message="获取回收站项目成功", data=response)


async def _restore_project(project_id: int, db: AsyncSession, user: User):
    project = await recycle_bin.restore_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回收站中不存在该项目")
    return success_response(message="项目已还原", data=ProjectInfoBase.model_validate(project))


async def _permanently_delete_project(project_id: int, db: AsyncSession, user: User):
    deleted = await recycle_bin.permanently_delete_project(db, project_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回收站中不存在该项目")
    return success_response(message="项目及其章节已彻底删除")


@router.post("/projects/{project_id}/trash")
async def move_project_to_trash(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _move_project(project_id, db, user)


@router.get("/projects")
async def get_recycled_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _list_projects(db, user)


@router.put("/projects/{project_id}/restore")
async def restore_project(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _restore_project(project_id, db, user)


@router.delete("/projects/{project_id}")
async def permanently_delete_project(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _permanently_delete_project(project_id, db, user)


@router.get("/chapters")
async def get_recycled_chapters(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    chapter_rows = await recycle_bin.get_recycled_chapters(db, user.id)
    response = [
        RecycledChapterInfo.model_validate(chapter).model_copy(update={"projectname": projectname, "project_status": project_status})
        for chapter, projectname, project_status in chapter_rows
    ]
    return success_response(message="获取回收站章节成功", data=response)


@router.post("/chapters/{chapter_id}/trash")
async def move_chapter_to_trash(
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chapter = await recycle_bin.move_chapter_to_recycle_bin(db, chapter_id, user.id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已在回收站或项目不可用")
    return success_response(message="章节已移入回收站", data=ChapterInfo.model_validate(chapter))


@router.put("/chapters/{chapter_id}/restore")
async def restore_chapter(
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        chapter = await recycle_bin.restore_chapter(db, chapter_id, user.id)
    except recycle_bin.ProjectInRecycleBinError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回收站中不存在该章节")
    return success_response(message="章节已还原", data=ChapterInfo.model_validate(chapter))


@router.delete("/chapters/{chapter_id}")
async def permanently_delete_chapter(
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = await recycle_bin.permanently_delete_chapter(db, chapter_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回收站中不存在该章节")
    return success_response(message="章节已彻底删除")


# 保留既有 URL，避免已接入客户端在切换到独立回收站路由时中断。
@legacy_router.delete("/delProject")
async def legacy_move_project_to_trash(
    project_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _move_project(project_id, db, user)


@legacy_router.get("/recycleBin")
async def legacy_get_recycled_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _list_projects(db, user)


@legacy_router.put("/restoreProject")
async def legacy_restore_project(
    project_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _restore_project(project_id, db, user)


@legacy_router.delete("/permanentlyDeleteProject")
async def legacy_permanently_delete_project(
    project_id: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _permanently_delete_project(project_id, db, user)
