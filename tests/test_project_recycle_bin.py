import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import db_conf
from config.db_conf import Base, get_db
from models.projects import Chapter, Project
from models.users import User, UserToken
from routers.projects import router
from routers import recycle_bin


class RecycleBinTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 仅使用独立内存数据库，绝不连接开发环境 MySQL。
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        @event.listens_for(self.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with self.sessions() as session:
            session.add_all([
                User(id=1, username="owner", password="not-used-in-token-tests"),
                User(id=2, username="other", password="not-used-in-token-tests"),
            ])
            await session.flush()
            session.add_all([
                UserToken(user_id=1, token="owner-token", expires_at=datetime.now() + timedelta(hours=1)),
                UserToken(user_id=2, token="other-token", expires_at=datetime.now() + timedelta(hours=1)),
            ])
            await session.commit()

        async def test_db():
            async with self.sessions() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app = FastAPI()
        app.include_router(router)
        app.include_router(recycle_bin.router)
        app.include_router(recycle_bin.legacy_router)
        app.dependency_overrides[get_db] = test_db
        self.client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer owner-token"},
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()

    async def seed_project(self, *, user_id=1, status="连载中", previous_status=None, chapter_count=2):
        async with self.sessions() as session:
            project = Project(
                user_id=user_id, projectname="测试小说", status=status,
                previous_status=previous_status, chapter_count=chapter_count, total_words=1200,
            )
            session.add(project)
            await session.flush()
            session.add_all([
                Chapter(project_id=project.id, chapter_number=number, chaptername=f"第{number}章")
                for number in range(1, chapter_count + 1)
            ])
            await session.commit()
            return project.id

    async def project_request(self, method, endpoint, project_id, **kwargs):
        return await self.client.request(method, f"/api/project/{endpoint}", params={"project_id": project_id}, **kwargs)


class ProjectRecycleBinTests(RecycleBinTestCase):
    async def test_recycle_and_restore_preserve_each_status_and_chapters(self):
        for original_status in ("连载中", "完结", "断更"):
            with self.subTest(status=original_status):
                project_id = await self.seed_project(status=original_status)
                response = await self.project_request("DELETE", "delProject", project_id)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["data"]["status"], "回收站")
                active = (await self.client.get("/api/project/projects")).json()["data"]
                self.assertNotIn(project_id, [project["id"] for project in active])
                recycled = (await self.client.get("/api/project/recycleBin")).json()["data"]
                self.assertIn(project_id, [project["id"] for project in recycled])
                async with self.sessions() as session:
                    project = await session.get(Project, project_id)
                    self.assertEqual(project.previous_status, original_status)
                    chapters = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).all()
                    self.assertEqual(len(chapters), 2)

                restored = await self.project_request("PUT", "restoreProject", project_id)
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.json()["data"]["status"], original_status)
                self.assertEqual(restored.json()["data"]["chapter_count"], 2)
                active = (await self.client.get("/api/project/projects")).json()["data"]
                self.assertIn(project_id, [project["id"] for project in active])
                recycled = (await self.client.get("/api/project/recycleBin")).json()["data"]
                self.assertNotIn(project_id, [project["id"] for project in recycled])
                async with self.sessions() as session:
                    self.assertIsNone((await session.get(Project, project_id)).previous_status)
                    chapters = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).all()
                    self.assertEqual(len(chapters), 2)

    async def test_legacy_recycled_project_restores_to_serializing(self):
        project_id = await self.seed_project(status="回收站")
        response = await self.project_request("PUT", "restoreProject", project_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "连载中")

    async def test_null_status_project_is_listed_and_can_be_recycled(self):
        project_id = await self.seed_project()
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            project.status = None
            await session.commit()
        active = await self.client.get("/api/project/projects")
        self.assertEqual(active.status_code, 200)
        self.assertIsNone(active.json()["data"][0]["status"])
        self.assertEqual((await self.project_request("DELETE", "delProject", project_id)).status_code, 200)
        restored = await self.project_request("PUT", "restoreProject", project_id)
        self.assertIsNone(restored.json()["data"]["status"])
        async with self.sessions() as session:
            self.assertIsNone((await session.get(Project, project_id)).status)

    async def test_permanent_delete_removes_chapters_but_not_other_projects(self):
        project_id = await self.seed_project(status="回收站")
        other_id = await self.seed_project(user_id=2, status="回收站")
        response = await self.project_request("DELETE", "permanentlyDeleteProject", project_id)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"])
        async with self.sessions() as session:
            self.assertIsNone(await session.get(Project, project_id))
            self.assertIsNotNone(await session.get(Project, other_id))
            self.assertEqual((await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).all(), [])
            self.assertEqual(len((await session.scalars(select(Chapter).where(Chapter.project_id == other_id))).all()), 2)
        self.assertEqual((await self.project_request("DELETE", "permanentlyDeleteProject", project_id)).status_code, 404)

    async def test_only_recycled_projects_can_be_restored_or_permanently_deleted(self):
        project_id = await self.seed_project()
        for method, endpoint in (("PUT", "restoreProject"), ("DELETE", "permanentlyDeleteProject")):
            self.assertEqual((await self.project_request(method, endpoint, project_id)).status_code, 404)
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).status, "连载中")
            self.assertEqual(len((await session.scalars(select(Chapter))).all()), 2)

    async def test_repeated_recycle_or_restore_is_rejected(self):
        project_id = await self.seed_project(status="完结")
        self.assertEqual((await self.project_request("DELETE", "delProject", project_id)).status_code, 200)
        self.assertEqual((await self.project_request("DELETE", "delProject", project_id)).status_code, 404)
        self.assertEqual((await self.project_request("PUT", "restoreProject", project_id)).status_code, 200)
        self.assertEqual((await self.project_request("PUT", "restoreProject", project_id)).status_code, 404)
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).status, "完结")

    async def test_owner_isolation_and_missing_projects(self):
        own_id = await self.seed_project(status="回收站")
        other_id = await self.seed_project(user_id=2, status="回收站")
        active_other_id = await self.seed_project(user_id=2)
        recycled = (await self.client.get("/api/project/recycleBin")).json()["data"]
        self.assertEqual([project["id"] for project in recycled], [own_id])
        for method, endpoint, project_id in (
            ("PUT", "restoreProject", other_id),
            ("DELETE", "permanentlyDeleteProject", other_id),
            ("DELETE", "delProject", active_other_id),
            ("PUT", "restoreProject", 999999),
            ("DELETE", "permanentlyDeleteProject", 999999),
        ):
            self.assertEqual((await self.project_request(method, endpoint, project_id)).status_code, 404)
        other_recycled = await self.client.get("/api/project/recycleBin", headers={"Authorization": "Bearer other-token"})
        self.assertEqual([project["id"] for project in other_recycled.json()["data"]], [other_id])

    async def test_invalid_ids_and_authentication(self):
        for method, endpoint in (("DELETE", "delProject"), ("PUT", "restoreProject"), ("DELETE", "permanentlyDeleteProject")):
            for project_id in (0, -1, "invalid"):
                self.assertEqual((await self.project_request(method, endpoint, project_id)).status_code, 422)
            no_token = await self.project_request(method, endpoint, 1, headers={"Authorization": ""})
            self.assertIn(no_token.status_code, (401, 403))
            invalid_token = await self.project_request(method, endpoint, 1, headers={"Authorization": "Bearer invalid-token"})
            self.assertEqual(invalid_token.status_code, 401)
        self.assertIn((await self.client.get("/api/project/recycleBin", headers={"Authorization": ""})).status_code, (401, 403))

    async def test_delete_failure_rolls_back_project_and_chapters(self):
        project_id = await self.seed_project(status="回收站")
        # 模拟 flush 已发出 DELETE，但 commit 失败，确认依赖会完整回滚。
        async def fail_commit(session):
            await session.flush()
            raise RuntimeError("simulated commit failure")

        with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new=fail_commit):
            with self.assertRaisesRegex(RuntimeError, "simulated commit failure"):
                await self.project_request("DELETE", "permanentlyDeleteProject", project_id)
        async with self.sessions() as session:
            self.assertIsNotNone(await session.get(Project, project_id))
            self.assertEqual(len((await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).all()), 2)


class ChapterRecycleBinTests(RecycleBinTestCase):
    async def chapter_ids(self, project_id):
        async with self.sessions() as session:
            return list(await session.scalars(
                select(Chapter.id).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
            ))

    async def chapter_request(self, action, chapter_id, **kwargs):
        method, suffix = {
            "trash": ("POST", "/trash"),
            "restore": ("PUT", "/restore"),
            "delete": ("DELETE", ""),
        }[action]
        return await self.client.request(method, f"/api/recycle-bin/chapters/{chapter_id}{suffix}", **kwargs)

    async def test_chapter_recycle_restore_preserves_number_and_updates_count(self):
        project_id = await self.seed_project(chapter_count=3)
        chapter_id = (await self.chapter_ids(project_id))[1]
        response = await self.chapter_request("trash", chapter_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["is_deleted"])
        self.assertEqual(response.json()["data"]["chapter_number"], 2)
        active = (await self.client.get(f"/api/project/{project_id}/chapters")).json()["data"]
        self.assertEqual([chapter["chapter_number"] for chapter in active], [1, 3])
        recycled = (await self.client.get("/api/recycle-bin/chapters")).json()["data"]
        self.assertEqual([chapter["id"] for chapter in recycled], [chapter_id])
        self.assertEqual(recycled[0]["projectname"], "测试小说")
        self.assertEqual(recycled[0]["project_status"], "连载中")
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).chapter_count, 2)
            self.assertEqual(len((await session.scalars(select(Chapter))).all()), 3)

        response = await self.chapter_request("restore", chapter_id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["is_deleted"])
        active = (await self.client.get(f"/api/project/{project_id}/chapters")).json()["data"]
        self.assertEqual([chapter["chapter_number"] for chapter in active], [1, 2, 3])
        self.assertEqual((await self.client.get("/api/recycle-bin/chapters")).json()["data"], [])
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).chapter_count, 3)
            self.assertEqual((await session.get(Project, project_id)).total_words, 1200)

    async def test_only_deleted_chapters_can_be_restored_or_permanently_deleted(self):
        project_id = await self.seed_project(chapter_count=1)
        chapter_id = (await self.chapter_ids(project_id))[0]
        for action in ("restore", "delete"):
            self.assertEqual((await self.chapter_request(action, chapter_id)).status_code, 404)
        self.assertEqual((await self.chapter_request("trash", chapter_id)).status_code, 200)
        self.assertEqual((await self.chapter_request("trash", chapter_id)).status_code, 404)
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).chapter_count, 0)
        self.assertEqual((await self.chapter_request("restore", chapter_id)).status_code, 200)
        self.assertEqual((await self.chapter_request("restore", chapter_id)).status_code, 404)

    async def test_chapter_permanent_delete_does_not_affect_siblings_or_project(self):
        project_id = await self.seed_project()
        chapter_id, sibling_id = await self.chapter_ids(project_id)
        await self.chapter_request("trash", chapter_id)
        self.assertEqual((await self.chapter_request("delete", chapter_id)).status_code, 200)
        self.assertEqual((await self.chapter_request("delete", chapter_id)).status_code, 404)
        async with self.sessions() as session:
            self.assertIsNone(await session.get(Chapter, chapter_id))
            self.assertIsNotNone(await session.get(Chapter, sibling_id))
            self.assertEqual((await session.get(Project, project_id)).chapter_count, 1)

    async def test_parent_project_restore_does_not_restore_individually_deleted_chapters(self):
        project_id = await self.seed_project(status="完结")
        chapter_id, active_id = await self.chapter_ids(project_id)
        await self.chapter_request("trash", chapter_id)
        response = await self.client.post(f"/api/recycle-bin/projects/{project_id}/trash")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.client.get(f"/api/project/{project_id}/chapters")).status_code, 404)
        self.assertEqual((await self.chapter_request("trash", active_id)).status_code, 404)
        response = await self.chapter_request("restore", chapter_id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("请先还原所属项目", response.json()["detail"])
        recycled = (await self.client.get("/api/recycle-bin/chapters")).json()["data"]
        self.assertEqual(recycled[0]["project_status"], "回收站")
        response = await self.client.put(f"/api/recycle-bin/projects/{project_id}/restore")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "完结")
        self.assertEqual(response.json()["data"]["chapter_count"], 1)
        active = (await self.client.get(f"/api/project/{project_id}/chapters")).json()["data"]
        self.assertEqual([chapter["id"] for chapter in active], [active_id])
        self.assertEqual((await self.chapter_request("restore", chapter_id)).status_code, 200)

    async def test_deleting_project_cascades_to_active_and_trashed_chapters(self):
        project_id = await self.seed_project()
        chapter_id = (await self.chapter_ids(project_id))[0]
        await self.chapter_request("trash", chapter_id)
        await self.client.post(f"/api/recycle-bin/projects/{project_id}/trash")
        self.assertEqual((await self.client.delete(f"/api/recycle-bin/projects/{project_id}")).status_code, 200)
        async with self.sessions() as session:
            self.assertIsNone(await session.get(Project, project_id))
            self.assertEqual((await session.scalars(select(Chapter))).all(), [])
        self.assertEqual((await self.client.get("/api/recycle-bin/chapters")).json()["data"], [])

    async def test_can_permanently_delete_trashed_chapter_while_parent_is_trashed(self):
        project_id = await self.seed_project()
        chapter_id = (await self.chapter_ids(project_id))[0]
        await self.chapter_request("trash", chapter_id)
        await self.client.post(f"/api/recycle-bin/projects/{project_id}/trash")
        self.assertEqual((await self.chapter_request("delete", chapter_id)).status_code, 200)
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).status, "回收站")
            self.assertEqual((await session.get(Project, project_id)).chapter_count, 1)

    async def test_chapter_owner_isolation_and_missing_resources(self):
        own_id = await self.seed_project()
        other_id = await self.seed_project(user_id=2)
        own_chapter_id = (await self.chapter_ids(own_id))[0]
        other_chapter_id = (await self.chapter_ids(other_id))[0]
        await self.chapter_request("trash", own_chapter_id)
        for action in ("trash", "restore", "delete"):
            self.assertEqual((await self.chapter_request(action, other_chapter_id)).status_code, 404)
            self.assertEqual((await self.chapter_request(action, 999999)).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/project/{other_id}/chapters")).status_code, 404)
        self.assertEqual((await self.client.get("/api/project/999999/chapters")).status_code, 404)
        other_headers = {"Authorization": "Bearer other-token"}
        self.assertEqual((await self.chapter_request("trash", other_chapter_id, headers=other_headers)).status_code, 200)
        self.assertEqual((await self.chapter_request("restore", other_chapter_id)).status_code, 404)
        self.assertEqual((await self.chapter_request("delete", other_chapter_id)).status_code, 404)
        own_list = (await self.client.get("/api/recycle-bin/chapters")).json()["data"]
        other_list = (await self.client.get("/api/recycle-bin/chapters", headers=other_headers)).json()["data"]
        self.assertEqual([chapter["id"] for chapter in own_list], [own_chapter_id])
        self.assertEqual([chapter["id"] for chapter in other_list], [other_chapter_id])

    async def test_new_routes_validate_ids_and_require_authentication(self):
        endpoints = [
            ("GET", "/api/recycle-bin/projects"),
            ("GET", "/api/recycle-bin/chapters"),
            ("GET", "/api/project/1/chapters"),
        ]
        for resource in ("chapters", "projects"):
            for method, suffix in (("POST", "/trash"), ("PUT", "/restore"), ("DELETE", "")):
                for invalid_id in (0, -1, "invalid"):
                    response = await self.client.request(method, f"/api/recycle-bin/{resource}/{invalid_id}{suffix}")
                    self.assertEqual(response.status_code, 422)
                endpoints.append((method, f"/api/recycle-bin/{resource}/1{suffix}"))
        for method, path in endpoints:
            response = await self.client.request(method, path, headers={"Authorization": ""})
            self.assertIn(response.status_code, (401, 403))

    async def test_chapter_operations_roll_back_flag_count_and_deletion_on_failure(self):
        async def fail_commit(session):
            await session.flush()
            raise RuntimeError("simulated commit failure")

        for action in ("trash", "restore", "delete"):
            with self.subTest(action=action):
                project_id = await self.seed_project()
                chapter_id = (await self.chapter_ids(project_id))[0]
                already_deleted = action != "trash"
                if already_deleted:
                    await self.chapter_request("trash", chapter_id)
                with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new=fail_commit):
                    with self.assertRaisesRegex(RuntimeError, "simulated commit failure"):
                        await self.chapter_request(action, chapter_id)
                async with self.sessions() as session:
                    self.assertEqual((await session.get(Chapter, chapter_id)).is_deleted, already_deleted)
                    self.assertEqual((await session.get(Project, project_id)).chapter_count, 1 if already_deleted else 2)

    async def test_null_status_project_supports_chapter_recycle_and_restore(self):
        project_id = await self.seed_project()
        async with self.sessions() as session:
            (await session.get(Project, project_id)).status = None
            await session.commit()
        chapter_id = (await self.chapter_ids(project_id))[0]
        self.assertEqual((await self.chapter_request("trash", chapter_id)).status_code, 200)
        self.assertEqual((await self.chapter_request("restore", chapter_id)).status_code, 200)


class ProjectSchemaUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def check_upgrade(self, *, existing_statuses, has_previous_status, has_is_deleted=True):
        columns = {"status": {"type": SimpleNamespace(enums=existing_statuses)}}
        if has_previous_status:
            columns["previous_status"] = {"type": None}
        connection = MagicMock()
        connection.dialect.name = "mysql"
        chapter_columns = {"is_deleted"} if has_is_deleted else set()
        connection.run_sync = AsyncMock(side_effect=[None, columns, chapter_columns])
        connection.execute = AsyncMock()
        engine = MagicMock()
        engine.begin.return_value.__aenter__.return_value = connection
        with patch.object(db_conf, "async_engine", engine):
            await db_conf.init_db()
        return [str(call.args[0]) for call in connection.execute.await_args_list]

    async def test_adds_missing_previous_status_column(self):
        statements = await self.check_upgrade(existing_statuses=["连载中", "完结", "断更", "回收站"], has_previous_status=False)
        self.assertEqual(len(statements), 1)
        self.assertIn("ADD COLUMN previous_status", statements[0])

    async def test_current_schema_is_not_altered(self):
        statements = await self.check_upgrade(existing_statuses=["连载中", "完结", "断更", "回收站"], has_previous_status=True)
        self.assertEqual(statements, [])

    async def test_legacy_schema_adds_recycle_status_and_previous_status(self):
        statements = await self.check_upgrade(existing_statuses=["连载中", "完结", "断更"], has_previous_status=False)
        self.assertEqual(len(statements), 2)
        self.assertIn("MODIFY COLUMN status", statements[0])
        self.assertIn("ADD COLUMN previous_status", statements[1])

    async def test_adds_chapter_soft_delete_flag_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE chapters ADD COLUMN is_deleted", statements[0])
        self.assertIn("NOT NULL DEFAULT 0", statements[0])


if __name__ == "__main__":
    unittest.main()
