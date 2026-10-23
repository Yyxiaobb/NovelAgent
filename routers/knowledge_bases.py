from pathlib import PurePath

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import AsyncSessionLocal, get_db
from models.knowledge_base import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from models.users import User
from schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseInfo,
    KnowledgeDocumentCreate,
    KnowledgeDocumentInfo,
)
from services.knowledge_rag import MAX_DOCUMENT_CHARS, index_document
from utils.auth import get_current_user
from utils.response import success_response


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


async def _owned_base(db: AsyncSession, base_id: int, user_id: int) -> KnowledgeBase | None:
    return await db.scalar(select(KnowledgeBase).where(
        KnowledgeBase.id == base_id, KnowledgeBase.user_id == user_id, KnowledgeBase.is_deleted.is_(False),
    ))


@router.get("")
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    bases = list((await db.scalars(
        select(KnowledgeBase).where(
            KnowledgeBase.user_id == user.id, KnowledgeBase.is_deleted.is_(False),
        ).order_by(KnowledgeBase.updated_at.desc())
    )).all())
    response = []
    for base in bases:
        counts = (await db.execute(select(
            func.count(KnowledgeDocument.id),
            func.sum(case((KnowledgeDocument.status == "ready", 1), else_=0)),
        ).where(KnowledgeDocument.knowledge_base_id == base.id))).one()
        response.append(KnowledgeBaseInfo(
            id=base.id, name=base.name, description=base.description,
            document_count=counts[0] or 0, ready_document_count=counts[1] or 0,
            created_at=base.created_at, updated_at=base.updated_at, is_deleted=base.is_deleted,
        ))
    return success_response(message="知识库列表获取成功", data=response)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    base = KnowledgeBase(user_id=user.id, name=payload.name.strip(), description=payload.description)
    if not base.name:
        raise HTTPException(status_code=422, detail="知识库名称不能为空")
    db.add(base)
    await db.commit()
    await db.refresh(base)
    return success_response(message="知识库已创建", data=KnowledgeBaseInfo(
        id=base.id, name=base.name, description=base.description,
        document_count=0, ready_document_count=0,
        created_at=base.created_at, updated_at=base.updated_at, is_deleted=base.is_deleted,
    ), http_status=status.HTTP_201_CREATED)


@router.delete("/{base_id}")
async def delete_knowledge_base(
    base_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    base = await _owned_base(db, base_id, user.id)
    if base is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    base.is_deleted = True
    await db.commit()
    return success_response(message="知识库已移入回收站", data={"id": base_id, "is_deleted": True})


@router.get("/{base_id}/documents")
async def list_documents(
    base_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    if await _owned_base(db, base_id, user.id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    documents = list((await db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == base_id)
        .order_by(KnowledgeDocument.created_at.desc())
    )).all())
    return success_response(message="文档列表获取成功", data=[KnowledgeDocumentInfo.model_validate(item) for item in documents])


@router.post("/{base_id}/documents", status_code=status.HTTP_202_ACCEPTED)
async def create_document(
    payload: KnowledgeDocumentCreate,
    background_tasks: BackgroundTasks,
    base_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    base = await _owned_base(db, base_id, user.id)
    if base is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    filename = PurePath(payload.filename.replace("\\", "/")).name
    if PurePath(filename).suffix.lower() not in {".txt", ".md", ".markdown"}:
        raise HTTPException(status_code=415, detail="目前仅支持 TXT 和 Markdown 文档")
    content = payload.content.replace("\x00", "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="文档内容不能为空")
    if len(content) > MAX_DOCUMENT_CHARS:
        raise HTTPException(status_code=413, detail="单个文档最多支持 100 万字符")
    document = KnowledgeDocument(
        knowledge_base_id=base.id, filename=filename, source_text=content, status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    background_tasks.add_task(index_document, document.id, AsyncSessionLocal)
    return success_response(
        message="文档已接收，正在后台建立索引",
        data=KnowledgeDocumentInfo.model_validate(document),
        http_status=status.HTTP_202_ACCEPTED,
    )


@router.post("/{base_id}/documents/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_document_index(
    background_tasks: BackgroundTasks,
    base_id: int = Path(..., gt=0), document_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    if await _owned_base(db, base_id, user.id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    document = await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id, KnowledgeDocument.knowledge_base_id == base_id,
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    document.status = "pending"
    document.error_message = None
    await db.commit()
    background_tasks.add_task(index_document, document.id, AsyncSessionLocal)
    return success_response(
        message="已重新提交索引",
        data={"id": document.id, "status": document.status},
        http_status=status.HTTP_202_ACCEPTED,
    )


@router.delete("/{base_id}/documents/{document_id}")
async def delete_document(
    base_id: int = Path(..., gt=0), document_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    if await _owned_base(db, base_id, user.id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在或无权访问")
    document = await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id, KnowledgeDocument.knowledge_base_id == base_id,
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    await db.delete(document)
    await db.commit()
    return success_response(message="文档已删除", data={"id": document_id})
