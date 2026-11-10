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
        created_chapter = await self.client.post(
            f"/api/project/{project_id}/chapters",
            json={"chapter_number": 1, "chaptername": "测试章", "content": "初稿正文"},
        )
        chapter_id = created_chapter.json()["data"]["id"]
        from crud.review_sessions import create_session
        review_payload = {
            "overall_score": 70,
            "summary": "需要继续打磨",
            "strengths": [],
            "issues": [{
                "id": "issue-1", "category": "style", "severity": "major",
                "evidence": "节奏较快", "suggestion": "补充过渡", "must_fix": False,
            }],
            "dimension_scores": {key: 70 for key in (
                "goal", "continuity", "character", "causality", "style", "pacing", "ending",
            )},
            "stop_recommendation": False,
        }
        async with self.sessions() as session:
            review_session = await create_session(
                session,
                user_id=user_id,
                project_id=project_id,
                chapter_id=chapter_id,
                initial_content="初稿正文",
                draft_content="初稿正文",
                generation_payload={"expected_words": 3000},
                review_history=[{"round": 1, "score": 70, "review": review_payload}],
                latest_review=review_payload,
                max_rounds=3,
                accept_score=85,
            )
            review_session_id = review_session.id
        review_session_response = await self.client.get(f"/api/agent/review-sessions/{review_session_id}")
        self.assertEqual(review_session_response.status_code, 200)
        self.assertEqual(review_session_response.json()["data"]["status"], "awaiting_review")
        applied = await self.client.post(
            f"/api/agent/review-sessions/{review_session_id}/apply",
            json={"content": "人工确认后的正文"},
        )
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["data"]["status"], "applied")
        from crud.review_sessions import get_session as get_review_session, save_session
        async with self.sessions() as session:
            persisted = await get_review_session(session, review_session_id, user_id)
            await save_session(
                session,
                persisted,
                last_continue_request_id="retry-key-123456",
                last_continue_response={
                    **applied.json()["data"],
                    "status": "completed",
                    "stop_reason": "threshold_reached",
                },
            )
        replayed = await self.client.post(
            f"/api/agent/review-sessions/{review_session_id}/continue",
            json={"request_id": "retry-key-123456", "decisions": []},
        )
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.json()["data"]["status"], "completed")
        stats = await self.client.get(f"/api/agent/review/stats?project_id={project_id}")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["data"]["total_jobs"], 0)
        self.assertEqual(stats.json()["data"]["human_review_sessions"], 1)
        self.assertEqual(stats.json()["data"]["human_review_session_statuses"]["applied"], 1)

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
