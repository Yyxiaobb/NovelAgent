from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from crud import projects
from config.db_conf import get_db
from models.users import User
from schemas.projects import ChapterInfo, ProjectRequest, ProjectInfoBase
from utils.auth import get_current_user
from utils.response import success_response


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
