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
        review_config = await self.client.get("/api/agent/review/config")
        self.assertEqual(review_config.status_code, 200)
        self.assertIn("enabled", review_config.json()["data"])
        self.assertNotIn("api_key", review_config.json()["data"])
        saved_preferences = await self.client.put("/api/agent/review/preferences", json={
            "enabled": True, "max_rounds": 2, "accept_score": 90, "manual_approval": True,
        })
        self.assertEqual(saved_preferences.status_code, 200)
        self.assertEqual((await self.client.get("/api/agent/review/preferences")).json()["data"]["max_rounds"], 2)
        projects_response = await self.client.get("/api/project/projects")
        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual(projects_response.json()["data"], [])

        created_project = await self.client.post("/api/project/newProject", json={"projectname": "测试作品"})
        project_id = created_project.json()["data"]["id"]
        project_preferences = await self.client.put(
            f"/api/agent/projects/{project_id}/review/preferences",
            json={"enabled": False, "max_rounds": 1},
        )
        self.assertEqual(project_preferences.status_code, 200)
        self.assertFalse(project_preferences.json()["data"]["enabled"])
        account_preferences = await self.client.get("/api/agent/review/preferences")
        self.assertTrue(account_preferences.json()["data"]["enabled"])
        project_defaults = await self.client.get(f"/api/agent/projects/{project_id}/review/preferences")
        self.assertEqual(project_defaults.json()["data"]["max_rounds"], 1)
        cleared_preferences = await self.client.put(
            f"/api/agent/projects/{project_id}/review/preferences",
            json={"enabled": None, "max_rounds": None},
        )
        self.assertEqual(cleared_preferences.status_code, 200)
        self.assertEqual(cleared_preferences.json()["data"], {})
        from crud.review_preferences import resolve_preferences
        user_id = (await self.client.get("/api/user/info")).json()["data"]["id"]
        async with self.sessions() as session:
            resolved = await resolve_preferences(session, user_id, project_id)
        self.assertEqual(resolved, {
            "enabled": True, "max_rounds": 2, "accept_score": 90, "manual_approval": True,
        })
        stats = await self.client.get(f"/api/agent/review/stats?project_id={project_id}")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["data"]["total_jobs"], 0)

        logged_out = await self.client.post("/api/user/logout")
        self.assertEqual(logged_out.status_code, 200)
        self.assertNotIn("novel-agent-session", self.client.cookies)
        self.assertEqual((await self.client.get("/api/user/info")).status_code, 401)
        self.assertEqual((await self.client.get("/api/agent/review/config")).status_code, 401)
        self.assertEqual((await self.client.get("/api/agent/review/preferences")).status_code, 401)

        logged_in = await self.client.post("/api/user/login", json=credentials)
        self.assertEqual(logged_in.status_code, 200)
        self.assertIn("novel-agent-session", self.client.cookies)
        self.assertEqual((await self.client.get("/api/user/info")).status_code, 200)


if __name__ == "__main__":
    unittest.main()
