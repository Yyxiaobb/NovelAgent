import unittest

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.db_conf import Base, get_db
from main import app
from models import generation, outline_versions, projects, story_memory, users, versions  # noqa: F401


class AuthRouteTests(unittest.IsolatedAsyncioTestCase):
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
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_register_login_and_logout_manage_browser_session_cookie(self):
        credentials = {"username": "writer", "password": "test-password-123"}

        registered = await self.client.post("/api/user/register", json=credentials)

        self.assertEqual(registered.status_code, 200)
        self.assertIn("novel-agent-session", self.client.cookies)
        cookie = next(item for item in registered.cookies.jar if item.name == "novel-agent-session")
        self.assertTrue(cookie.has_nonstandard_attr("HttpOnly"))
        self.assertIn("Max-Age=86400", registered.headers["set-cookie"])
        self.assertEqual((await self.client.get("/api/user/info")).status_code, 200)
        projects_response = await self.client.get("/api/project/projects")
        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual(projects_response.json()["data"], [])

        logged_out = await self.client.post("/api/user/logout")
        self.assertEqual(logged_out.status_code, 200)
        self.assertNotIn("novel-agent-session", self.client.cookies)
        self.assertEqual((await self.client.get("/api/user/info")).status_code, 401)

        logged_in = await self.client.post("/api/user/login", json=credentials)
        self.assertEqual(logged_in.status_code, 200)
        self.assertIn("novel-agent-session", self.client.cookies)
        self.assertEqual((await self.client.get("/api/user/info")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
