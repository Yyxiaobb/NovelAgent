from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select

from schemas.projects import ProjectRequest
from models.projects import Chapter, Project

async def get_projects(db: AsyncSession, user_id: int):
    query = select(Project).where(
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    )
    result = await db.execute(query)
    projects = result.scalars().all()
    return projects

async def create_new_pro(db: AsyncSession, pro_data: ProjectRequest, user_id: int):
    new_pro = Project(projectname=pro_data.projectname, introduction=pro_data.introduction, user_id=user_id)
    db.add(new_pro)
    await db.commit()
    await db.refresh(new_pro)
    return new_pro


async def get_project_chapters(db: AsyncSession, project_id: int, user_id: int):
    project_query = select(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
    )
    project_result = await db.execute(project_query)
    if project_result.scalar_one_or_none() is None:
        return None

    query = select(Chapter).join(Project).where(
        Project.id == project_id,
        Project.user_id == user_id,
        or_(Project.status.is_(None), Project.status != "回收站"),
        Chapter.is_deleted.is_(False),
    ).order_by(Chapter.chapter_number, Chapter.id)
    result = await db.execute(query)
    return result.scalars().all()
