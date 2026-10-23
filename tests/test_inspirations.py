import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.db_conf import Base, get_db
from main import app
from models.inspiration import Inspiration


class InspirationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def override_get_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        await self.client.post("/api/user/register", json={"username": "inspiration-owner", "password": "password-123"})

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_create_edit_refine_recycle_restore_and_permanently_delete(self):
        created = await self.client.post("/api/inspirations", json={"title": "城市钟表", "content": "修表匠能听见城市的记忆"})
        self.assertEqual(created.status_code, 201)
        item_id = created.json()["data"]["id"]

        updated = await self.client.put(
            f"/api/inspirations/{item_id}",
            json={"title": "会说话的钟", "content": "修表匠能听见城市的记忆", "refined_content": None},
        )
        self.assertEqual(updated.status_code, 200)

        with patch("routers.inspirations.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value="完善后的故事提案")
            refined = await self.client.post(f"/api/inspirations/{item_id}/refine")
        self.assertEqual(refined.status_code, 200)
        self.assertEqual(refined.json()["data"]["refined_content"], "完善后的故事提案")

        deleted = await self.client.delete(f"/api/inspirations/{item_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual((await self.client.get("/api/inspirations")).json()["data"], [])
        recycled = await self.client.get("/api/recycle-bin/inspirations")
        self.assertEqual(recycled.status_code, 200)
        self.assertEqual(recycled.json()["data"][0]["title"], "会说话的钟")

        restored = await self.client.put(f"/api/recycle-bin/inspirations/{item_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(len((await self.client.get("/api/inspirations")).json()["data"]), 1)

        await self.client.delete(f"/api/inspirations/{item_id}")
        purged = await self.client.delete(f"/api/recycle-bin/inspirations/{item_id}")
        self.assertEqual(purged.status_code, 200)
        async with self.sessions() as session:
            self.assertIsNone(await session.scalar(select(Inspiration).where(Inspiration.id == item_id)))


if __name__ == "__main__":
    unittest.main()
