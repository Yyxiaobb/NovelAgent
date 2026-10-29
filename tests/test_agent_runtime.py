import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agent.runtime import _execute, run_agent
from agent.skills import load_skill
from agent.prompts import PROMPTS, get_prompt_template, render_prompt


def _response(*, content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_round_trip_uses_project_scoped_tool_and_returns_final_text(self):
        db = object()
        tool_call = SimpleNamespace(id="call-1", function=SimpleNamespace(
            name="get_project_context", arguments="{}"))
        client = SimpleNamespace(acompletion=AsyncMock(side_effect=[
            _response(tool_calls=[tool_call]), _response(content='{"objective":"推进主线"}')
        ]))

        async def fake_execute(name, arguments, session, *, project_id, user_id):
            self.assertEqual((name, arguments, session, project_id, user_id),
                             ("get_project_context", "{}", db, 9, 4))
            return json.dumps({"projectname": "测试作品"}, ensure_ascii=False)

        from unittest.mock import patch
        with patch("agent.runtime._execute", side_effect=fake_execute):
            result = await run_agent(client, [{"role": "user", "content": "规划"}], db,
                                     project_id=9, user_id=4, max_tokens=300)
        self.assertEqual(result, '{"objective":"推进主线"}')
        self.assertEqual(client.acompletion.await_count, 2)
        self.assertEqual(client.acompletion.await_args.kwargs["tool_choice"], "auto")

    async def test_invalid_and_unknown_tool_arguments_fail_closed(self):
        db = object()
        invalid = await _execute("search_story_memory", "{", db, project_id=1, user_id=1)
        unknown = await _execute("run_shell", "{}", db, project_id=1, user_id=1)
        self.assertIn("有效 JSON", json.loads(invalid)["error"])
        self.assertEqual(json.loads(unknown)["error"], "未知工具")

    async def test_chapter_context_tools_are_project_scoped_and_bounded(self):
        from unittest.mock import patch

        chapter = SimpleNamespace(
            chapter_number=3, chaptername="关隘", plan={"objective": "通关"},
            summary="主角找到密道", memory={"character_state": "受伤"},
            content="正文" * 1000,
        )
        with patch("agent.runtime.projects.get_chapter", new=AsyncMock(return_value=chapter)) as get_chapter:
            chapter_result = json.loads(await _execute(
                "get_chapter", '{"chapter_id": 7}', object(), project_id=9, user_id=4,
            ))
        get_chapter.assert_awaited_once_with(unittest.mock.ANY, 9, 7, 4)
        self.assertEqual(chapter_result["summary"], "主角找到密道")
        self.assertNotIn("chaptername", chapter_result)
        self.assertEqual(len(chapter_result["content_excerpt"]), 1200)

        prior = [SimpleNamespace(
            chapter_number=2, chaptername="前夜", summary="暴风将至", memory={"timeline": "黄昏"},
        )]
        with (
            patch("agent.runtime.projects.get_project", new=AsyncMock(return_value=object())) as get_project,
            patch("agent.runtime.projects.get_prior_chapter_memories", new=AsyncMock(return_value=prior)) as get_prior,
        ):
            memories = json.loads(await _execute(
                "get_recent_chapter_memories",
                '{"before_chapter_number": 3, "limit": 4}', object(), project_id=9, user_id=4,
            ))
        get_project.assert_awaited_once_with(unittest.mock.ANY, 9, 4)
        get_prior.assert_awaited_once_with(unittest.mock.ANY, 9, 3, limit=4)
        self.assertNotIn("summary", memories[0])
        self.assertEqual(memories[0]["memory"]["timeline"], "黄昏")
        self.assertNotIn("chaptername", memories[0])

    async def test_chapter_context_tool_rejects_invalid_or_cross_project_ids(self):
        from unittest.mock import patch

        invalid = await _execute("get_chapter", '{"chapter_id": -1}', object(), project_id=9, user_id=4)
        self.assertIn("参数无效", json.loads(invalid)["error"])
        with patch("agent.runtime.projects.get_chapter", new=AsyncMock(return_value=None)):
            inaccessible = await _execute("get_chapter", '{"chapter_id": 7}', object(), project_id=9, user_id=4)
        self.assertIn("不可访问", json.loads(inaccessible)["error"])

    async def test_round_budget_stops_unbounded_tool_loop(self):
        call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="unknown", arguments="{}"))
        client = SimpleNamespace(acompletion=AsyncMock(return_value=_response(tool_calls=[call])))
        with self.assertRaisesRegex(ValueError, "model-round limit"):
            await run_agent(client, [{"role": "user", "content": "x"}], object(),
                            project_id=1, user_id=1, max_tokens=20)
        self.assertEqual(client.acompletion.await_count, 5)

    async def test_prompt_and_skill_are_versioned_and_task_scoped(self):
        template, prompt = render_prompt("chapter_plan", project_id=1, chapter_id=2,
                                         project_type="科幻",
                                         project_introduction="简介", project_outline="大纲",
                                         chapter_number=1,
                                         expected_words=1200, user_idea="营救")
        skill = load_skill("chapter-planning", task_type="chapter_plan")
        self.assertEqual(template.version, "1.0.0")
        self.assertIn("用户想法：营救", prompt)
        self.assertNotIn("测试作品", prompt)
        self.assertNotIn("启航", prompt)
        self.assertEqual(skill.version, "1.0.0")
        with self.assertRaises(ValueError):
            load_skill("../agent.py", task_type="chapter_plan")

    def test_prompt_registry_covers_each_generation_scene(self):
        expected = {
            "project_field", "idea_refinement", "project_outline",
            "outline_volume_planner", "outline_volume_executor", "chapter_plan", "chapter_content", "chapter_memory",
        }
        self.assertTrue(expected.issubset(PROMPTS))
        for template_id in expected:
            template = get_prompt_template(template_id)
            self.assertEqual(template.id, template_id)
            self.assertTrue(template.version)
            self.assertTrue(template.system)
            self.assertTrue(template.task_template)

    def test_outline_volume_agent_prompts_plan_and_execute_from_full_book_outline(self):
        template, prompt = render_prompt(
            "outline_volume_planner",
            project_type="科幻",
            project_introduction="一段星际旅程",
            expected_words=1000000,
            project_outline="主角追查异常信号，最终发现宇宙循环的真相。",
            user_idea="重点描写人物成长",
        )
        self.assertEqual(template.version, "1.0.0")
        self.assertIn("全书目标总字数：1000000 字", prompt)
        self.assertIn("宇宙循环的真相", prompt)
        self.assertIn("各卷字数之和必须等于全书目标字数", prompt)
        self.assertIn('"volumes"', prompt)

        executor, execution_prompt = render_prompt(
            "outline_volume_executor",
            project_type="科幻",
            project_introduction="一段星际旅程",
            expected_words=1000000,
            project_outline="主角追查异常信号，最终发现宇宙循环的真相。",
            volume_plan="全书分卷计划 JSON",
            current_volume="第一卷执行计划",
            previous_volumes="前序卷纲",
            reference_context="参考资料",
        )
        self.assertIn("Planner 的完整分卷计划", execution_prompt)
        self.assertIn("当前执行任务", execution_prompt)
        self.assertIn("前序卷已生成卷纲", execution_prompt)
        self.assertNotIn("星河归途", prompt + execution_prompt)
        self.assertEqual(executor.id, "outline_volume_executor")


if __name__ == "__main__":
    unittest.main()
