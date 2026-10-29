import logging
import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from crud import generation as generation_crud
from crud import projects
from crud import versions as chapter_versions
from crud import outline_versions, outline_volume_versions
from config.db_conf import get_db
from config.queue_conf import enqueue_memory_job
from models.users import User
from schemas.projects import ChapterInfo, ChapterRequest, ChapterVersionInfo, OutlineInfo, OutlineRequest, OutlineVersionInfo, OutlineVolumeInfo, OutlineVolumeRequest, OutlineVolumeVersionInfo, ProjectRequest, ProjectInfoBase, ProjectStateInfo, ProjectStateRequest
from schemas.media import ImageUploadRequest
from utils.auth import get_current_user
from utils.response import success_response
from services.project_export import render_project_export
from utils.media import save_data_url


router = APIRouter(prefix="/api/project", tags=["projects"])
logger = logging.getLogger(__name__)


async def _queue_chapter_memory_update(db: AsyncSession, *, user_id: int, project_id: int, chapter_id: int) -> None:
    active_job = await generation_crud.get_active_memory_job(
        db, project_id=project_id, chapter_id=chapter_id,
    )
    # A queued job will read the latest saved text when the worker starts. If
    # one is already running, queue one follow-up so a concurrent edit is not lost.
    if active_job is not None and active_job.status == "queued":
        return
    job_id = uuid.uuid4().hex
    await generation_crud.create_chapter_memory_job(
        db,
        job_id=job_id,
        user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    try:
        await enqueue_memory_job(job_id)
    except Exception:
        # The durable queued row is recovered by worker startup if Redis is
        # temporarily unavailable; saving the chapter must still succeed.
        logger.exception("failed to enqueue chapter memory job %s", job_id)

@router.get("/projects")
async def get_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project_list = await projects.get_projects(db, user.id)
    response = [
        ProjectInfoBase.model_validate(project).model_dump(exclude={"current_state_markdown"})
        for project in project_list
    ]
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


@router.get("/{project_id}/outline/volumes")
async def get_outline_volumes(
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    volumes = await projects.get_outline_volumes(db, project.id)
    return success_response(message="获取卷纲成功", data=[OutlineVolumeInfo.model_validate(item) for item in volumes])


@router.post("/{project_id}/outline/volumes")
async def create_outline_volume(
    payload: OutlineVolumeRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    volume = await projects.create_outline_volume(db, project.id, payload)
    return success_response(message="卷纲已创建", data=OutlineVolumeInfo.model_validate(volume))


@router.put("/{project_id}/outline/volumes/{volume_id}")
async def update_outline_volume(
    payload: OutlineVolumeRequest,
    project_id: int = Path(..., gt=0),
    volume_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    volume = await projects.update_outline_volume(db, project.id, volume_id, user.id, payload)
    if volume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="卷纲不存在")
    return success_response(message="卷纲已保存", data=OutlineVolumeInfo.model_validate(volume))


@router.delete("/{project_id}/outline/volumes/{volume_id}")
async def delete_outline_volume(
    project_id: int = Path(..., gt=0),
    volume_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    if not await projects.delete_outline_volume(db, project.id, volume_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="卷纲不存在")
    return success_response(message="卷纲已移入回收站", data={"id": volume_id})


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


@router.get("/{project_id}/outline/volume-versions")
async def get_outline_volume_versions(
    project_id: int = Path(..., gt=0), limit: int = 100,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    versions = await outline_volume_versions.list_versions(db, project.id, user.id, limit)
    return success_response(message="获取卷纲版本成功", data=[OutlineVolumeVersionInfo.model_validate(item) for item in versions])


@router.post("/{project_id}/outline/volume-versions/{version_id}/restore")
async def restore_outline_volume_version(
    project_id: int = Path(..., gt=0), version_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    version = await outline_volume_versions.get_version(db, version_id, project.id, user.id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="卷纲版本不存在或无权访问")
    restored = await outline_volume_versions.restore_version(db, project, version, user.id)
    return success_response(message="卷纲版本已恢复", data=OutlineVolumeInfo.model_validate(restored))


@router.get("/{project_id}/outline/rolling-versions")
async def get_rolling_outline_versions(
    project_id: int = Path(..., gt=0), limit: int = 100,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    versions = await chapter_versions.list_project_plan_versions(db, project.id, user.id, limit)
    return success_response(message="获取滚动细纲版本成功", data=[ChapterVersionInfo.model_validate(item) for item in versions])


@router.post("/{project_id}/outline/rolling-versions/{version_id}/restore")
async def restore_rolling_outline_version(
    project_id: int = Path(..., gt=0), version_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    project = await projects.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作品不存在或已在回收站")
    version = await chapter_versions.get_project_plan_version(db, version_id, project.id, user.id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="滚动细纲版本不存在或无权访问")
    chapter = await projects.get_chapter(db, project.id, version.chapter_id, user.id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="所属章节不存在或不可用")
    restored = await chapter_versions.restore_plan(db, chapter, version, user.id)
    return success_response(message="滚动细纲版本已恢复", data=ChapterInfo.model_validate(restored))


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


@router.put("/{project_id}/state")
async def update_project_state(
    payload: ProjectStateRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await projects.update_project_state(
        db, project_id, user.id, payload.current_state_markdown,
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    return success_response(
        message="当前状态已保存",
        data=ProjectStateInfo(
            project_id=project.id,
            current_state_markdown=project.current_state_markdown or "",
            updated_at=project.updated_at,
        ),
    )


@router.post("/{project_id}/chapters")
async def create_chapter(
    chapter_data: ChapterRequest,
    project_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        chapter = await projects.create_chapter(db, project_id, user.id, chapter_data)
    except (projects.ChapterNumberConflictError, projects.ChapterVolumeConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在或已在回收站")
    if (chapter.content or "").strip():
        await _queue_chapter_memory_update(
            db, user_id=user.id, project_id=project_id, chapter_id=chapter.id,
        )
    return success_response(message="章节创建成功", data=ChapterInfo.model_validate(chapter))


@router.put("/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    chapter_data: ChapterRequest,
    project_id: int = Path(..., gt=0),
    chapter_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await projects.get_chapter(db, project_id, chapter_id, user.id)
    should_queue_memory = bool(
        existing is not None
        and (chapter_data.content or "").strip()
        and "summary" not in chapter_data.model_fields_set
        and "memory" not in chapter_data.model_fields_set
        and (chapter_data.content != (existing.content or "") or not existing.summary)
    )
    try:
        chapter = await projects.update_chapter(db, project_id, chapter_id, user.id, chapter_data)
    except (projects.ChapterNumberConflictError, projects.ChapterVolumeConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在、已删除或项目不可用")
    if should_queue_memory:
        await _queue_chapter_memory_update(
            db, user_id=user.id, project_id=project_id, chapter_id=chapter_id,
        )
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
    has_restored_content = bool((version.content or "").strip())
    restored = await chapter_versions.restore_version(db, chapter, version, user.id)
    if has_restored_content:
        await _queue_chapter_memory_update(
            db, user_id=user.id, project_id=project_id, chapter_id=chapter_id,
        )
    return success_response(message="章节版本已恢复", data=ChapterInfo.model_validate(restored))
