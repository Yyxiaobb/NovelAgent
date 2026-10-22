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

    async def test_round_budget_stops_unbounded_tool_loop(self):
        call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="unknown", arguments="{}"))
        client = SimpleNamespace(acompletion=AsyncMock(return_value=_response(tool_calls=[call])))
        with self.assertRaisesRegex(ValueError, "model-round limit"):
            await run_agent(client, [{"role": "user", "content": "x"}], object(),
                            project_id=1, user_id=1, max_tokens=20)
        self.assertEqual(client.acompletion.await_count, 5)

    async def test_prompt_and_skill_are_versioned_and_task_scoped(self):
        template, prompt = render_prompt("chapter_plan", project_id=1, chapter_id=2,
                                         project_name="测试作品", project_type="科幻",
                                         project_introduction="简介", project_outline="大纲",
                                         chapter_number=1, chapter_name="启航",
                                         expected_words=1200, user_idea="营救")
        skill = load_skill("chapter-planning", task_type="chapter_plan")
        self.assertEqual(template.version, "1.0.0")
        self.assertIn("用户想法：营救", prompt)
        self.assertIn("作品名称：测试作品", prompt)
        self.assertEqual(skill.version, "1.0.0")
        with self.assertRaises(ValueError):
            load_skill("../agent.py", task_type="chapter_plan")

    def test_prompt_registry_covers_each_generation_scene(self):
        expected = {
            "project_field", "idea_refinement", "project_outline",
            "chapter_plan", "chapter_content", "chapter_memory",
        }
        self.assertTrue(expected.issubset(PROMPTS))
        for template_id in expected:
            template = get_prompt_template(template_id)
            self.assertEqual(template.id, template_id)
            self.assertTrue(template.version)
            self.assertTrue(template.system)
            self.assertTrue(template.task_template)


if __name__ == "__main__":
    unittest.main()
