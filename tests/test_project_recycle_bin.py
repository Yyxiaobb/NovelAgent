import json
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
from models.story_memory import StoryMemory, StoryMemoryEvent
from models.users import User, UserToken
from routers.projects import router
from routers import agent, recycle_bin, story_memory


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
        app.include_router(agent.router)
        app.include_router(story_memory.router)
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


class ProjectEditingTests(RecycleBinTestCase):
    async def test_story_memory_crud_is_project_scoped_and_used_for_generation(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).one()
            chapter.chaptername = "北境来信"
            chapter_id = chapter.id
            await session.commit()

        created = await self.client.post(
            f"/api/project/{project_id}/memories",
            json={
                "category": "character", "title": "沈砚", "content": "沈砚答应护送信使前往北境。",
                "keywords": ["沈砚", "信使", "北境"], "source_chapter_id": chapter_id,
            },
        )
        self.assertEqual(created.status_code, 200)
        memory_id = created.json()["data"]["id"]

        listed = await self.client.get(f"/api/project/{project_id}/memories")
        self.assertEqual(len(listed.json()["data"]), 1)
        self.assertEqual(listed.json()["data"][0]["title"], "沈砚")

        self.client.headers["Authorization"] = "Bearer other-token"
        forbidden = await self.client.get(f"/api/project/{project_id}/memories")
        self.assertEqual(forbidden.status_code, 404)
        self.client.headers["Authorization"] = "Bearer owner-token"

        with patch("routers.agent.LLMClient") as llm_class:
            llm_class.return_value.__aenter__.return_value.achat = AsyncMock(return_value="风雪中的信使停下脚步。")
            generated = await self.client.post(
                f"/api/agent/projects/{project_id}/chapters/{chapter_id}/content",
                json={"expected_words": 1800, "user_idea": "沈砚带信使沿北境小路前行"},
            )
        self.assertEqual(generated.status_code, 200)
        prompt = llm_class.return_value.__aenter__.return_value.achat.await_args.args[0][1]["content"]
        self.assertIn("沈砚答应护送信使前往北境", prompt)

        updated = await self.client.put(
            f"/api/project/{project_id}/memories/{memory_id}",
            json={
                "category": "character", "title": "沈砚", "content": "沈砚已将信使送抵北境。",
                "keywords": ["沈砚", "北境"], "source_chapter_id": chapter_id, "is_active": False,
            },
        )
        self.assertFalse(updated.json()["data"]["is_active"])
        deleted = await self.client.delete(f"/api/project/{project_id}/memories/{memory_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual((await self.client.get(f"/api/project/{project_id}/memories")).json()["data"], [])

    async def test_story_memory_batch_review_and_conflict_detection(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).one()
            chapter_id = chapter.id

        payloads = [
            {"category": "character", "title": "沈砚", "content": "沈砚在北境寻找信使。", "keywords": ["沈砚", "北境"]},
            {"category": "character", "title": "沈砚", "content": "沈砚在北境保护信使。", "keywords": ["沈砚", "北境"]},
        ]
        ids = []
        for payload in payloads:
            payload["source_chapter_id"] = chapter_id
            response = await self.client.post(f"/api/project/{project_id}/memories", json=payload)
            self.assertEqual(response.status_code, 200)
            ids.append(response.json()["data"]["id"])

        conflicts = await self.client.get(f"/api/project/{project_id}/memories/conflicts")
        self.assertEqual(conflicts.status_code, 200)
        self.assertEqual(conflicts.json()["data"][0]["reason"], "same_title")

        for memory_id in ids:
            async with self.sessions() as session:
                memory = await session.get(StoryMemory, memory_id)
                memory.origin = "chapter_extract"
                memory.review_status = "pending"
                memory.is_active = False
                await session.commit()
        batch = await self.client.post(
            f"/api/project/{project_id}/memories/batch-review",
            json={"memory_ids": ids, "decision": "approved"},
        )
        self.assertEqual(batch.status_code, 200)
        self.assertTrue(all(item["is_active"] for item in batch.json()["data"]))

    async def test_story_memory_merge_keeps_target_and_records_audit_event(self):
        project_id = await self.seed_project(chapter_count=1)
        payloads = [
            {"category": "world", "title": "北境", "content": "北境常年风雪。", "keywords": ["北境", "风雪"]},
            {"category": "world", "title": "北境规则补充", "content": "北境的关隘在冬季关闭。", "keywords": ["北境", "关隘"]},
        ]
        ids = []
        for payload in payloads:
            response = await self.client.post(f"/api/project/{project_id}/memories", json=payload)
            ids.append(response.json()["data"]["id"])
        merged = await self.client.post(
            f"/api/project/{project_id}/memories/merge",
            json={"target_id": ids[0], "source_ids": [ids[1]]},
        )
        self.assertEqual(merged.status_code, 200)
        self.assertIn("关隘", merged.json()["data"]["content"])
        async with self.sessions() as session:
            source = await session.get(StoryMemory, ids[1])
            event = (await session.scalars(select(StoryMemoryEvent).where(StoryMemoryEvent.project_id == project_id))).one()
            self.assertEqual(source.merged_into_id, ids[0])
            self.assertEqual(event.event_type, "merge")
        events = await self.client.get(f"/api/project/{project_id}/memories/events")
        self.assertEqual(events.status_code, 200)
        self.assertEqual(events.json()["data"][0]["event_type"], "merge")

    async def test_story_memory_undo_restores_update_and_review(self):
        project_id = await self.seed_project(chapter_count=1)
        created = await self.client.post(
            f"/api/project/{project_id}/memories",
            json={"category": "character", "title": "沈砚", "content": "初始状态", "keywords": ["初始"]},
        )
        memory_id = created.json()["data"]["id"]
        updated = await self.client.put(
            f"/api/project/{project_id}/memories/{memory_id}",
            json={"category": "character", "title": "沈砚新名", "content": "修改状态", "keywords": ["修改"]},
        )
        self.assertEqual(updated.status_code, 200)
        undone = await self.client.post(f"/api/project/{project_id}/memories/{memory_id}/undo")
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.json()["data"]["title"], "沈砚")
        self.assertEqual(undone.json()["data"]["content"], "初始状态")

        async with self.sessions() as session:
            memory = await session.get(StoryMemory, memory_id)
            memory.origin = "chapter_extract"
            memory.review_status = "pending"
            memory.is_active = False
            await session.commit()
        reviewed = await self.client.post(
            f"/api/project/{project_id}/memories/{memory_id}/review", json={"decision": "approved"},
        )
        self.assertEqual(reviewed.status_code, 200)
        reverted = await self.client.post(f"/api/project/{project_id}/memories/{memory_id}/undo")
        self.assertEqual(reverted.status_code, 200)
        self.assertEqual(reverted.json()["data"]["review_status"], "pending")
        self.assertFalse(reverted.json()["data"]["is_active"])
        duplicate = await self.client.post(f"/api/project/{project_id}/memories/{memory_id}/undo")
        self.assertEqual(duplicate.status_code, 409)

    async def test_story_memory_undo_merge_restores_sources(self):
        project_id = await self.seed_project(chapter_count=1)
        ids = []
        for title, content in (("北境", "常年风雪"), ("北境补充", "冬季封关")):
            response = await self.client.post(
                f"/api/project/{project_id}/memories",
                json={"category": "world", "title": title, "content": content, "keywords": ["北境"]},
            )
            ids.append(response.json()["data"]["id"])
        merged = await self.client.post(
            f"/api/project/{project_id}/memories/merge",
            json={"target_id": ids[0], "source_ids": [ids[1]]},
        )
        self.assertEqual(merged.status_code, 200)
        undone = await self.client.post(f"/api/project/{project_id}/memories/{ids[0]}/undo")
        self.assertEqual(undone.status_code, 200)
        async with self.sessions() as session:
            target = await session.get(StoryMemory, ids[0])
            source = await session.get(StoryMemory, ids[1])
            self.assertEqual(target.content, "常年风雪")
            self.assertIsNone(source.merged_into_id)
            self.assertTrue(source.is_active)
            self.assertEqual(source.review_status, "approved")

    async def test_project_exports_markdown_and_txt_with_only_active_chapters(self):
        project_id = await self.seed_project(chapter_count=2)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            project.projectname = "风起山海"
            project.project_type = "奇幻"
            project.introduction = "少年踏上寻龙之旅。"
            project.outline = "第一卷：山海初遇"
            chapters = list((await session.scalars(
                select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
            )).all())
            chapters[0].chaptername = "初入山海"
            chapters[0].content = "群山之外，少年抬头望见巨龙。"
            chapters[1].chaptername = "已删除章节"
            chapters[1].content = "这部分已经移入回收站。"
            chapters[1].is_deleted = True
            await session.commit()

        markdown = await self.client.get(f"/api/project/{project_id}/export/markdown")
        self.assertEqual(markdown.status_code, 200)
        self.assertIn("filename*=UTF-8''", markdown.headers["content-disposition"])
        self.assertIn("# 风起山海", markdown.text)
        self.assertIn("## 故事大纲", markdown.text)
        self.assertIn("### 第 1 章 初入山海", markdown.text)
        self.assertNotIn("这部分已经移入回收站", markdown.text)

        text_export = await self.client.get(f"/api/project/{project_id}/export/txt")
        self.assertEqual(text_export.status_code, 200)
        self.assertIn("%E9%A3%8E%E8%B5%B7%E5%B1%B1%E6%B5%B7.txt", text_export.headers["content-disposition"])
        self.assertIn("第 1 章 初入山海", text_export.text)
        self.assertNotIn("已删除章节", text_export.text)

        self.client.headers["Authorization"] = "Bearer other-token"
        forbidden = await self.client.get(f"/api/project/{project_id}/export/markdown")
        self.assertEqual(forbidden.status_code, 404)

    async def test_project_and_chapter_saves_are_committed(self):
        project_id = await self.seed_project(chapter_count=1)

        project_response = await self.client.put(
            f"/api/project/{project_id}",
            json={
                "projectname": "已保存作品",
                "introduction": "已保存简介",
                "project_type": "科幻",
                "cover_url": "https://example.com/saved-cover.jpg",
                "status": "完结",
            },
        )
        self.assertEqual(project_response.status_code, 200)

        async with self.sessions() as session:
            saved_project = await session.get(Project, project_id)
            self.assertEqual(saved_project.projectname, "已保存作品")
            self.assertEqual(saved_project.introduction, "已保存简介")
            self.assertEqual(saved_project.project_type, "科幻")
            self.assertEqual(saved_project.cover_url, "https://example.com/saved-cover.jpg")
            self.assertEqual(saved_project.status, "完结")
            chapter = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).first()
            chapter_id = chapter.id

        chapter_response = await self.client.put(
            f"/api/project/{project_id}/chapters/{chapter_id}",
            json={"chapter_number": 3, "chaptername": "已保存章节"},
        )
        self.assertEqual(chapter_response.status_code, 200)

        new_chapter_response = await self.client.post(
            f"/api/project/{project_id}/chapters",
            json={"chapter_number": 4, "chaptername": "新增章节", "content": "新增内容"},
        )
        self.assertEqual(new_chapter_response.status_code, 200)
        duplicate_response = await self.client.post(
            f"/api/project/{project_id}/chapters",
            json={"chapter_number": 4, "chaptername": "重复编号"},
        )
        self.assertEqual(duplicate_response.status_code, 409)

        async with self.sessions() as session:
            saved_chapter = await session.get(Chapter, chapter_id)
            self.assertEqual(saved_chapter.chapter_number, 3)
            self.assertEqual(saved_chapter.chaptername, "已保存章节")
            added_id = new_chapter_response.json()["data"]["id"]
            added_chapter = await session.get(Chapter, added_id)
            self.assertEqual(added_chapter.chaptername, "新增章节")
            self.assertEqual(added_chapter.content, "新增内容")
            saved_project = await session.get(Project, project_id)
            self.assertEqual(saved_project.chapter_count, 2)

    async def test_project_stats_follow_active_chapter_content(self):
        project_id = await self.seed_project(chapter_count=0)
        created = await self.client.post(
            f"/api/project/{project_id}/chapters",
            json={"chapter_number": 1, "chaptername": "第一章", "content": "星河启航"},
        )
        self.assertEqual(created.status_code, 200)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            self.assertEqual(project.chapter_count, 1)
            self.assertEqual(project.total_words, 4)

        chapter_id = created.json()["data"]["id"]
        updated = await self.client.put(
            f"/api/project/{project_id}/chapters/{chapter_id}",
            json={"chapter_number": 1, "chaptername": "第一章", "content": "星河启航，开始远行"},
        )
        self.assertEqual(updated.status_code, 200)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            self.assertEqual(project.total_words, 9)

        self.assertEqual((await self.client.post(f"/api/recycle-bin/chapters/{chapter_id}/trash")).status_code, 200)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            self.assertEqual((project.chapter_count, project.total_words), (0, 0))

        self.assertEqual((await self.client.put(f"/api/recycle-bin/chapters/{chapter_id}/restore")).status_code, 200)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            self.assertEqual((project.chapter_count, project.total_words), (1, 9))

    async def test_outline_save_is_committed(self):
        project_id = await self.seed_project(chapter_count=0)
        response = await self.client.put(
            f"/api/project/{project_id}/outline",
            json={"outline": "第一幕：相遇\n第二幕：远行"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["outline"], "第一幕：相遇\n第二幕：远行")
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            self.assertEqual(project.outline, "第一幕：相遇\n第二幕：远行")

    async def test_generate_outline_uses_project_context_and_persists_target_words(self):
        project_id = await self.seed_project(chapter_count=0)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            project.project_type = "科幻"
            project.introduction = "探险队穿越深空，寻找失落的家园。"
            project.projectname = "星河归途"
            await session.commit()

        with patch("routers.agent.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value="第一卷：星海启程")
            response = await self.client.post(
                f"/api/agent/projects/{project_id}/outline",
                json={"expected_words": 120000, "user_idea": "双主角视角，结局温暖"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["outline"], "第一卷：星海启程")
        self.assertEqual(response.json()["data"]["expected_words"], 120000)
        prompt = client.achat.await_args.args[0][1]["content"]
        self.assertIn("作品类型：科幻", prompt)
        self.assertIn("约 120000 字", prompt)
        self.assertIn("双主角视角，结局温暖", prompt)
        async with self.sessions() as session:
            self.assertEqual((await session.get(Project, project_id)).expected_words, 120000)

    async def test_generate_outline_rejects_invalid_word_count_and_missing_project(self):
        project_id = await self.seed_project(chapter_count=0)
        invalid = await self.client.post(
            f"/api/agent/projects/{project_id}/outline", json={"expected_words": 0},
        )
        self.assertEqual(invalid.status_code, 422)
        missing = await self.client.post(
            "/api/agent/projects/9999/outline", json={"expected_words": 100000},
        )
        self.assertEqual(missing.status_code, 404)

    async def test_generate_chapter_content_uses_project_outline_and_chapter_context(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            project = await session.get(Project, project_id)
            project.project_type = "科幻"
            project.introduction = "探险队寻找失落家园。"
            project.outline = "第一卷：穿越深空"
            chapter = (await session.execute(select(Chapter).where(Chapter.project_id == project_id))).scalar_one()
            chapter.chaptername = "启航"
            chapter_id = chapter.id
            await session.commit()

        with patch("routers.agent.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value="飞船缓缓驶离港口。")
            response = await self.client.post(
                f"/api/agent/projects/{project_id}/chapters/{chapter_id}/content",
                json={"expected_words": 2500, "user_idea": "结尾出现新的线索"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["content"], "飞船缓缓驶离港口。")
        prompt = client.achat.await_args.args[0][1]["content"]
        self.assertIn("作品类型：科幻", prompt)
        self.assertIn("第一卷：穿越深空", prompt)
        self.assertIn("第 1 章", prompt)
        self.assertIn("约 2500 字", prompt)
        self.assertIn("结尾出现新的线索", prompt)

    async def test_generate_chapter_content_uses_prior_chapter_memory(self):
        project_id = await self.seed_project(chapter_count=2)
        async with self.sessions() as session:
            chapters = list((await session.scalars(
                select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
            )).all())
            chapters[0].summary = "主角在遗迹中获得了残缺地图。"
            chapters[0].memory = {
                "character_state": "主角决定追查地图来源",
                "setting_changes": "遗迹出现未知能量",
                "unresolved_threads": "地图指向北境关隘",
                "timeline": "启航后的第三天",
            }
            chapter_id = chapters[1].id
            await session.commit()

        with patch("routers.agent.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value="北境关隘外，风雪骤起。")
            response = await self.client.post(
                f"/api/agent/projects/{project_id}/chapters/{chapter_id}/content",
                json={"expected_words": 1800},
            )

        self.assertEqual(response.status_code, 200)
        prompt = client.achat.await_args.args[0][1]["content"]
        self.assertIn("主角在遗迹中获得了残缺地图", prompt)
        self.assertIn("主角决定追查地图来源", prompt)
        self.assertIn("地图指向北境关隘", prompt)

    async def test_generate_chapter_memory_persists_summary_and_structured_memory(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).one()
            chapter.content = "主角在雨夜救下信使，并得知王城即将封锁。"
            chapter_id = chapter.id
            await session.commit()

        generated = {
            "summary": "主角救下信使，得知王城即将封锁。",
            "character_state": "主角决定护送信使",
            "setting_changes": "王城即将封锁",
            "unresolved_threads": "信使携带的密函来源不明",
            "timeline": "雨夜，王城封锁前",
        }
        with patch("routers.agent.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value=json.dumps(generated, ensure_ascii=False))
            response = await self.client.post(
                f"/api/agent/projects/{project_id}/chapters/{chapter_id}/memory",
                json={"user_idea": "只记录正文明确发生的事情"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["summary"], generated["summary"])
        self.assertEqual(response.json()["data"]["memory"], {key: generated[key] for key in generated if key != "summary"})
        async with self.sessions() as session:
            saved = await session.get(Chapter, chapter_id)
            self.assertEqual(saved.summary, generated["summary"])
            self.assertEqual(saved.memory["unresolved_threads"], generated["unresolved_threads"])

        pending = (await self.client.get(f"/api/project/{project_id}/memories")).json()["data"]
        suggestions = [item for item in pending if item["origin"] == "chapter_extract"]
        self.assertEqual(len(suggestions), 4)
        self.assertTrue(all(item["review_status"] == "pending" and not item["is_active"] for item in suggestions))

        character_suggestion = next(item for item in suggestions if item["category"] == "character")
        review_response = await self.client.post(
            f"/api/project/{project_id}/memories/{character_suggestion['id']}/review",
            json={"decision": "approved"},
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["data"]["review_status"], "approved")
        self.assertTrue(review_response.json()["data"]["is_active"])
        reject_response = await self.client.post(
            f"/api/project/{project_id}/memories/{suggestions[1]['id']}/review",
            json={"decision": "rejected"},
        )
        self.assertEqual(reject_response.json()["data"]["review_status"], "rejected")

    async def test_generate_chapter_memory_rejects_empty_content_and_invalid_json(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter = (await session.scalars(select(Chapter).where(Chapter.project_id == project_id))).one()
            chapter_id = chapter.id

        empty = await self.client.post(f"/api/agent/projects/{project_id}/chapters/{chapter_id}/memory", json={})
        self.assertEqual(empty.status_code, 422)

        async with self.sessions() as session:
            (await session.get(Chapter, chapter_id)).content = "已有正文"
            await session.commit()
        with patch("routers.agent.LLMClient") as llm_class:
            client = llm_class.return_value.__aenter__.return_value
            client.achat = AsyncMock(return_value="不是 JSON")
            invalid = await self.client.post(f"/api/agent/projects/{project_id}/chapters/{chapter_id}/memory", json={})
        self.assertEqual(invalid.status_code, 502)

    async def test_generate_chapter_content_rejects_invalid_length_or_resource(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter = (await session.execute(select(Chapter).where(Chapter.project_id == project_id))).scalar_one()
            chapter_id = chapter.id
        invalid = await self.client.post(
            f"/api/agent/projects/{project_id}/chapters/{chapter_id}/content",
            json={"expected_words": 0},
        )
        self.assertEqual(invalid.status_code, 422)
        missing = await self.client.post(
            f"/api/agent/projects/{project_id}/chapters/9999/content",
            json={"expected_words": 3000},
        )
        self.assertEqual(missing.status_code, 404)

    async def test_chapter_plan_can_be_saved_and_read_back(self):
        project_id = await self.seed_project(chapter_count=1)
        async with self.sessions() as session:
            chapter_id = (await session.execute(select(Chapter.id).where(Chapter.project_id == project_id))).scalar_one()
        plan = {
            "objective": "完成第一次启航",
            "conflict": "主角面对未知信号",
            "key_events": "离港；发现信号；决定追踪",
            "ending_hook": "信号来自船内",
            "expected_words": 3000,
        }
        response = await self.client.put(
            f"/api/project/{project_id}/chapters/{chapter_id}",
            json={"chapter_number": 1, "chaptername": "启航", "content": "正文", "plan": plan},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["plan"], plan)
        detail = await self.client.get(f"/api/project/{project_id}/chapters/{chapter_id}")
        self.assertEqual(detail.json()["data"]["plan"], plan)


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
            # The project word count is rebuilt from active chapter content;
            # these fixture chapters have no content, so the count is zero.
            self.assertEqual((await session.get(Project, project_id)).total_words, 0)

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
    async def check_upgrade(self, *, existing_statuses, has_previous_status, has_is_deleted=True, has_project_type=True, has_cover_url=True, has_outline=True, has_expected_words=True, has_content=True, has_plan=True, has_summary=True, has_memory=True):
        columns = {"status": {"type": SimpleNamespace(enums=existing_statuses)}}
        if has_previous_status:
            columns["previous_status"] = {"type": None}
        if has_project_type:
            columns["project_type"] = {"type": None}
        if has_cover_url:
            columns["cover_url"] = {"type": None}
        if has_outline:
            columns["outline"] = {"type": None}
        if has_expected_words:
            columns["expected_words"] = {"type": None}
        connection = MagicMock()
        connection.dialect.name = "mysql"
        chapter_columns = {"is_deleted"} if has_is_deleted else set()
        if has_content:
            chapter_columns.add("content")
        if has_plan:
            chapter_columns.add("plan")
        if has_summary:
            chapter_columns.add("summary")
        if has_memory:
            chapter_columns.add("memory")
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

    async def test_adds_project_type_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_project_type=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE project ADD COLUMN project_type", statements[0])

    async def test_adds_cover_url_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True,
            has_project_type=True, has_cover_url=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE project ADD COLUMN cover_url", statements[0])

    async def test_adds_outline_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_project_type=True,
            has_cover_url=True, has_outline=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE project ADD COLUMN outline", statements[0])

    async def test_adds_expected_words_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_project_type=True,
            has_cover_url=True, has_outline=True, has_expected_words=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE project ADD COLUMN expected_words", statements[0])
        self.assertIn("INT NULL", statements[0])

    async def test_adds_chapter_content_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_content=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE chapters ADD COLUMN content", statements[0])

    async def test_adds_chapter_plan_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_content=True, has_plan=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE chapters ADD COLUMN plan", statements[0])

    async def test_adds_chapter_summary_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_content=True, has_plan=True,
            has_summary=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE chapters ADD COLUMN summary", statements[0])

    async def test_adds_chapter_memory_for_existing_rows(self):
        statements = await self.check_upgrade(
            existing_statuses=["连载中", "完结", "断更", "回收站"],
            has_previous_status=True, has_is_deleted=True, has_content=True, has_plan=True,
            has_summary=True, has_memory=False,
        )
        self.assertEqual(len(statements), 1)
        self.assertIn("ALTER TABLE chapters ADD COLUMN memory", statements[0])


if __name__ == "__main__":
    unittest.main()
