import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from services.chapter_generation import (
    ChapterContentContext,
    build_content_segments,
    ContentQualityError,
    MAX_PROMPT_CHARACTERS,
    _fit_prompt_budget,
    generate_content,
    is_retryable_generation_error,
    stream_content,
    validate_content_quality,
)
from schemas.projects import ChapterPlan


class ChapterGenerationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = ChapterContentContext(
            project=SimpleNamespace(id=1),
            chapter=SimpleNamespace(id=2),
            plan=ChapterPlan(
                objective="推进故事", conflict="遭遇阻碍", key_events="发现线索",
                ending_hook="留下悬念", expected_words=3000,
            ),
            prompt="请生成这一章",
            citations=[],
        )

    async def test_sync_generation_uses_shared_messages_and_parameters(self):
        expected = "正文内容。" * 50
        client = SimpleNamespace(achat=AsyncMock(return_value=f"  {expected}  "), model="test-model")

        @asynccontextmanager
        async def client_factory():
            yield client

        content, model = await generate_content(self.context, client_factory, lambda words: words * 2)

        self.assertEqual((content, model), (expected, "test-model"))
        client.achat.assert_awaited_once_with(
            self.context.messages, temperature=0.8, max_tokens=6000,
        )

    async def test_sync_generation_repairs_invalid_output_once(self):
        expected = "修复后的章节正文。" * 30
        client = SimpleNamespace(
            achat=AsyncMock(side_effect=["以下是正文：太短", expected]), model="test-model",
        )

        @asynccontextmanager
        async def client_factory():
            yield client

        content, _ = await generate_content(self.context, client_factory, lambda words: words * 2)

        self.assertEqual(content, expected)
        self.assertEqual(client.achat.await_count, 2)
        repair_messages = client.achat.await_args_list[1].args[0]
        self.assertIn("质量检查", repair_messages[-1]["content"])
        self.assertEqual(client.achat.await_args_list[1].kwargs["temperature"], 0.55)

    async def test_stream_generation_uses_same_messages_and_parameters(self):
        async def chunks(*args, **kwargs):
            yield "第一段"
            yield "第二段"

        client = SimpleNamespace(astream=Mock(side_effect=chunks), model="test-model")

        @asynccontextmanager
        async def client_factory():
            yield client

        received = [part async for part in stream_content(
            self.context, client_factory, lambda words: words * 2,
        )]

        self.assertEqual(received, ["第一段", "第二段"])
        self.assertEqual(client.astream.call_args.args[0], self.context.messages)
        self.assertEqual(client.astream.call_args.kwargs, {"temperature": 0.8, "max_tokens": 6000})

    def test_quality_gate_rejects_meta_text_leaks_and_short_output(self):
        for content in (
            "",
            "太短",
            "以下是正文：" + "故事" * 100,
            "```text\n" + "故事" * 100 + "\n```",
            "system prompt " + "故事" * 100,
        ):
            with self.subTest(content=content[:20]), self.assertRaises(ContentQualityError):
                validate_content_quality(content, 3000)

    def test_quality_gate_accepts_prose_near_minimum_length(self):
        validate_content_quality("故事的发展。" * 40, 3000)

    def test_prompt_budget_bounds_large_context_and_preserves_prompt_edges(self):
        prompt = "系统与背景" * 7000 + "\n本章目标与用户要求"

        bounded = _fit_prompt_budget(prompt)

        self.assertLessEqual(len(bounded), MAX_PROMPT_CHARACTERS)
        self.assertIn("系统与背景", bounded[:500])
        self.assertTrue(bounded.endswith("本章目标与用户要求"))

    def test_background_retry_policy_only_retries_transient_provider_errors(self):
        from agent import LLMRequestError

        self.assertTrue(is_retryable_generation_error(LLMRequestError("network")))
        self.assertTrue(is_retryable_generation_error(LLMRequestError("rate limited", 429)))
        self.assertTrue(is_retryable_generation_error(LLMRequestError("upstream", 503)))
        self.assertFalse(is_retryable_generation_error(LLMRequestError("unauthorized", 401)))
        self.assertFalse(is_retryable_generation_error(LLMRequestError("bad request", 400)))

    def test_long_chapter_is_split_by_ordered_key_events(self):
        long_context = ChapterContentContext(
            project=self.context.project,
            chapter=self.context.chapter,
            plan=self.context.plan.model_copy(update={
                "expected_words": 17000,
                "key_events": "抵达边城；发现密道；与守军交锋",
            }),
            prompt=self.context.prompt,
            citations=self.context.citations,
        )

        segments = build_content_segments(long_context)

        self.assertEqual(len(segments), 3)
        self.assertEqual(sum(words for words, _ in segments), 17000)
        self.assertEqual([event for _, event in segments], ["抵达边城", "发现密道", "与守军交锋"])


if __name__ == "__main__":
    unittest.main()
