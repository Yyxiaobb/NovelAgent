import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.db_conf import Base, get_db
from main import app
from models.knowledge_base import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from services.knowledge_rag import _cosine, retrieve_knowledge, split_text


class KnowledgeRagUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_split_text_preserves_overlap_and_content(self):
        text = "甲" * 90 + "。" + "乙" * 90 + "。" + "丙" * 90
        chunks = split_text(text, chunk_size=120, overlap=20)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(all(chunks))
        self.assertGreater(len(set(chunks[0]) & set(chunks[1])), 0)

    def test_cosine_similarity_orders_matching_vector_first(self):
        self.assertGreater(_cosine([1.0, 0.0], [0.9, 0.1]), _cosine([1.0, 0.0], [0.0, 1.0]))

    async def test_retrieval_is_owner_scoped_and_ranked(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with sessions() as db:
                owner = KnowledgeBase(user_id=1, name="设定库")
                other = KnowledgeBase(user_id=2, name="他人资料")
                db.add_all([owner, other])
                await db.flush()
                owner_doc = KnowledgeDocument(
                    knowledge_base_id=owner.id, filename="world.md", source_text="资料", status="ready",
                )
                other_doc = KnowledgeDocument(
                    knowledge_base_id=other.id, filename="private.md", source_text="私密", status="ready",
                )
                db.add_all([owner_doc, other_doc])
                await db.flush()
                db.add_all([
                    KnowledgeChunk(document_id=owner_doc.id, chunk_index=0, content="王城位于北境", embedding=[1.0, 0.0]),
                    KnowledgeChunk(document_id=owner_doc.id, chunk_index=1, content="港口贸易繁荣", embedding=[0.2, 0.8]),
                    KnowledgeChunk(document_id=other_doc.id, chunk_index=0, content="不可泄露", embedding=[1.0, 0.0]),
                ])
                await db.commit()

                with patch("services.knowledge_rag.embed_texts", new=AsyncMock(return_value=[[1.0, 0.0]])):
                    result = await retrieve_knowledge(
                        db, user_id=1, knowledge_base_ids=[owner.id], query="北境王城",
                    )

                self.assertEqual(result[0]["excerpt"], "王城位于北境")
                self.assertTrue(all(item["knowledge_base_id"] == owner.id for item in result))
                with self.assertRaises(PermissionError):
                    await retrieve_knowledge(db, user_id=1, knowledge_base_ids=[other.id], query="私密")
        finally:
            await engine.dispose()


class KnowledgeBaseRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def override_get_db():
            async with self.sessions() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        await self.client.post("/api/user/register", json={"username": "knowledge-owner", "password": "password-123"})

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_create_import_list_and_recycle_restore_and_permanent_delete(self):
        created = await self.client.post("/api/knowledge-bases", json={"name": "世界观", "description": "设定资料"})
        self.assertEqual(created.status_code, 201)
        base_id = created.json()["data"]["id"]

        with patch("routers.knowledge_bases.index_document", new=AsyncMock()) as index_document:
            imported = await self.client.post(
                f"/api/knowledge-bases/{base_id}/documents",
                json={"filename": "rules.md", "content": "# 魔法规则\n施法必须支付代价。"},
            )
        self.assertEqual(imported.status_code, 202)
        document_id = imported.json()["data"]["id"]
        index_document.assert_awaited_once()

        documents = await self.client.get(f"/api/knowledge-bases/{base_id}/documents")
        self.assertEqual(documents.status_code, 200)
        self.assertEqual(documents.json()["data"][0]["filename"], "rules.md")

        async with self.sessions() as db:
            db.add(KnowledgeChunk(document_id=document_id, chunk_index=0, content="施法必须支付代价。", embedding=[1.0]))
            await db.commit()

        deleted = await self.client.delete(f"/api/knowledge-bases/{base_id}")
        self.assertEqual(deleted.status_code, 200)
        async with self.sessions() as db:
            base = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == base_id))
            self.assertIsNotNone(base)
            self.assertTrue(base.is_deleted)
            self.assertEqual(await db.scalar(select(func.count()).select_from(KnowledgeDocument)), 1)
            self.assertEqual(await db.scalar(select(func.count()).select_from(KnowledgeChunk)), 1)

        self.assertEqual((await self.client.get("/api/knowledge-bases")).json()["data"], [])
        recycled = await self.client.get("/api/recycle-bin/knowledge-bases")
        self.assertEqual(recycled.status_code, 200)
        self.assertEqual(len(recycled.json()["data"]), 1)

        restored = await self.client.put(f"/api/recycle-bin/knowledge-bases/{base_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.json()["data"]["is_deleted"])
        await self.client.delete(f"/api/knowledge-bases/{base_id}")
        permanently_deleted = await self.client.delete(f"/api/recycle-bin/knowledge-bases/{base_id}")
        self.assertEqual(permanently_deleted.status_code, 200)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(KnowledgeBase)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(KnowledgeDocument)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(KnowledgeChunk)), 0)

    async def test_document_type_and_user_isolation_are_enforced(self):
        base = await self.client.post("/api/knowledge-bases", json={"name": "私有资料"})
        base_id = base.json()["data"]["id"]
        unsupported = await self.client.post(
            f"/api/knowledge-bases/{base_id}/documents",
            json={"filename": "notes.pdf", "content": "content"},
        )
        self.assertEqual(unsupported.status_code, 415)

        other = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        try:
            await other.post("/api/user/register", json={"username": "knowledge-other", "password": "password-123"})
            response = await other.get(f"/api/knowledge-bases/{base_id}/documents")
            self.assertEqual(response.status_code, 404)
        finally:
            await other.aclose()


if __name__ == "__main__":
    unittest.main()
