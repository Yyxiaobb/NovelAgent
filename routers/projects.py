from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from crud import projects
from crud import versions as chapter_versions
from crud import outline_versions
from config.db_conf import get_db
from models.users import User
from schemas.projects import ChapterInfo, ChapterRequest, ChapterVersionInfo, OutlineInfo, OutlineRequest, OutlineVersionInfo, ProjectRequest, ProjectInfoBase
from schemas.media import ImageUploadRequest
from utils.auth import get_current_user
from utils.response import success_response
from services.project_export import render_project_export
from utils.media import save_data_url


router = APIRouter(prefix="/api/project", tags=["projects"])

@router.get("/projects")
async def get_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project_list = await projects.get_projects(db, user.id)
    response = [ProjectInfoBase.model_validate(project) for project in project_list]
    return success_response(message="获取项目成功", data=response)

@router.post("/newProject")
async def createProject(project_data: ProjectRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project = await projects.create_new_pro(db, project_data, user.id)
    response = ProjectInfoBase.model_validate(project)
    return success_response(message="项目创建成功", data=response)


@router.get("/detail/{project_id}")
async def get_project_detail(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="获取项目详情成功", data=ProjectInfoBase.model_validate(project))

@router.get("/{project_id}/chapters")
async def get_project_chapters(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chapter_list = await projects.get_project_chapters(db, project_id, user.id)
    if chapter_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")

    response = [ChapterInfo.model_validate(chapter) for chapter in chapter_list]
    return success_response(message="获取章节成功", data=response)


@router.post("/{project_id}/cover/upload")
async def upload_project_cover(
    payload: ImageUploadRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    project.cover_url = save_data_url(payload.data_url, "covers")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return success_response(message="作品封面上传成功", data=ProjectInfoBase.model_validate(project))


@router.get("/{project_id}/export/{file_format}")
async def export_project(
    project_id: int = Path(..., gt=0),
    file_format: Literal["markdown", "txt"] = Path(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    chapters = await projects.get_project_chapters(db, project_id, user.id)
    content = render_project_export(project, chapters or [], file_format)
    extension = "md" if file_format == "markdown" else "txt"
    title = (project.projectname or "未命名作品").strip() or "未命名作品"
    filename = f"{title}.{extension}"
    disposition = f"attachment; filename=project-{project_id}.{extension}; filename*=UTF-8''{quote(filename)}"
    media_type = "text/markdown" if file_format == "markdown" else "text/plain"
    return Response(
        content=content.encode("utf-8"),
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


@router.get("/{project_id}/outline")
async def get_project_outline(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project_outline(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="获取作品大纲成功", data=OutlineInfo(project_id=project.id, outline=project.outline))


@router.put("/{project_id}/outline")
async def update_project_outline(
    outline_data: OutlineRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.update_project_outline(db, project_id, user.id, outline_data)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="作品大纲已保存", data=OutlineInfo(project_id=project.id, outline=project.outline))


@router.get("/{project_id}/outline/versions")
async def get_outline_versions(
    project_id: int = Path(..., gt=0),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    versions = await outline_versions.list_versions(db, project.id, user.id, limit)
    return success_response(message="获取大纲版本成功", data=[OutlineVersionInfo.model_validate(item) for item in versions])


@router.post("/{project_id}/outline/versions/{version_id}/restore")
async def restore_outline_version(
    project_id: int = Path(..., gt=0),
    version_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    version = await outline_versions.get_version(db, version_id, project.id, user.id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="大纲版本不存在或无权访问")
    restored = await outline_versions.restore_version(db, project, version, user.id)
    return success_response(message="大纲版本已恢复", data=OutlineInfo(project_id=restored.id, outline=restored.outline))


@router.get("/{project_id}/chapters/{chapter_id}")
async def get_chapter_detail(
    project_id: int = Path(..., gt=0),
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chapter = await projects.get_chapter(db, project_id, chapter_id, user.id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已删除或项目不可用")
    return success_response(message="获取章节详情成功", data=ChapterInfo.model_validate(chapter))


@router.put("/{project_id:int}")
async def update_project(
    project_data: ProjectRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.update_project(db, project_id, user.id, project_data)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="项目更新成功", data=ProjectInfoBase.model_validate(project))


@router.post("/{project_id}/chapters")
async def create_chapter(
    chapter_data: ChapterRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        chapter = await projects.create_chapter(db, project_id, user.id, chapter_data)
    except projects.ChapterNumberConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(message="章节创建成功", data=ChapterInfo.model_validate(chapter))


@router.put("/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    chapter_data: ChapterRequest,
    project_id: int = Path(..., gt=0),
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        chapter = await projects.update_chapter(db, project_id, chapter_id, user.id, chapter_data)
    except projects.ChapterNumberConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已删除或项目不可用")
    return success_response(message="章节更新成功", data=ChapterInfo.model_validate(chapter))


@router.get("/{project_id}/chapters/{chapter_id}/versions")
async def get_chapter_versions(
    project_id: int = Path(..., gt=0),
    chapter_id: int = Path(..., gt=0),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chapter = await projects.get_chapter(db, project_id, chapter_id, user.id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已删除或项目不可用")
    versions = await chapter_versions.list_versions(db, chapter.id, user.id, limit)
    return success_response(message="获取章节版本成功", data=[ChapterVersionInfo.model_validate(item) for item in versions])


@router.post("/{project_id}/chapters/{chapter_id}/versions/{version_id}/restore")
async def restore_chapter_version(
    project_id: int = Path(..., gt=0),
    chapter_id: int = Path(..., gt=0),
    version_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chapter = await projects.get_chapter(db, project_id, chapter_id, user.id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已删除或项目不可用")
    version = await chapter_versions.get_version(db, version_id, chapter.id, user.id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节版本不存在或无权访问")
    restored = await chapter_versions.restore_version(db, chapter, version, user.id)
    return success_response(message="章节版本已恢复", data=ChapterInfo.model_validate(restored))
