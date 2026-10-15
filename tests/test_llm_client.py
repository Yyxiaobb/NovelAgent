import asyncio
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI, OpenAI

from agent import (
    LLMClient, LLMConfig, LLMConfigurationError, LLMError,
    LLMRequestError, LLMResponseError, NovelAgent,
)


SETTINGS = {"model": "test-model", "api_key": "unit-test-key", "base_url": "https://llm.test/v1"}
MESSAGES = [{"role": "user", "content": "写一个故事开场"}]


def completion(content="海港的灯亮了。", **message_fields):
    return {
        "id": "test-completion", "object": "chat.completion", "created": 1,
        "model": "test-model",
        "choices": [{
            "index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": content, **message_fields},
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11},
    }


def event(content=None, *, choices=None):
    payload = {
        "id": "test-stream", "object": "chat.completion.chunk", "created": 1,
        "model": "test-model", "choices": choices if choices is not None else [
            {"index": 0, "delta": {"content": content}, "finish_reason": None},
        ],
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()


class TrackingStream(httpx.SyncByteStream):
    def __init__(self, events, error=None):
        self.events = events
        self.error = error
        self.closed = False

    def __iter__(self):
        yield from self.events
        if self.error:
            raise self.error
        yield b"data: [DONE]\n\n"

    def close(self):
        self.closed = True


class AsyncTrackingStream(httpx.AsyncByteStream):
    def __init__(self, events, error=None):
        self.events = events
        self.error = error
        self.closed = False

    async def __aiter__(self):
        for value in self.events:
            yield value
        if self.error:
            raise self.error
        yield b"data: [DONE]\n\n"

    async def aclose(self):
        self.closed = True


class EnvironmentCase(unittest.TestCase):
    def setUp(self):
        # 不读取开发者 .env，不允许测试使用真实模型配置。
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        self.dotenv = patch("agent.LLMclient.load_dotenv").start()


class LLMConfigTests(EnvironmentCase):
    def test_requires_model_key_and_url(self):
        for name in ("model", "api_key", "base_url"):
            with self.subTest(field=name):
                config = {**SETTINGS, name: None}
                with self.assertRaises(LLMConfigurationError):
                    LLMClient(**config)

    def test_prefixed_environment_variables_and_legacy_fallback(self):
        os.environ.update({
            "MODEL": "legacy-model", "API_KEY": "legacy-key", "BASE_URL": "https://old.test/v1",
            "LLM_MODEL": "preferred-model", "LLM_API_KEY": "preferred-key",
            "LLM_BASE_URL": "https://preferred.test/v1", "LLM_TIMEOUT": "12.5",
            "LLM_MAX_RETRIES": "0", "LLM_PROVIDER": "test-provider",
        })
        config = LLMConfig.from_env()
        self.assertEqual(config.model, "preferred-model")
        self.assertEqual(config.api_key, "preferred-key")
        self.assertEqual(config.base_url, "https://preferred.test/v1")
        self.assertEqual(config.provider, "test-provider")
        self.assertEqual(config.timeout, 12.5)
        self.assertEqual(config.max_retries, 0)
        for name in ("LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
            del os.environ[name]
        legacy = LLMConfig.from_env()
        self.assertEqual((legacy.model, legacy.api_key, legacy.base_url), (
            "legacy-model", "legacy-key", "https://old.test/v1",
        ))

    def test_explicit_parameters_override_env_and_dotenv_preserves_environment(self):
        os.environ.update({"LLM_MODEL": "environment-model", "LLM_TIMEOUT": "bad", "LLM_MAX_RETRIES": "bad"})
        config = LLMConfig.from_env(**SETTINGS, timeout=5, max_retries=0)
        self.assertEqual(config.model, "test-model")
        self.assertEqual(config.timeout, 5)
        self.assertEqual(config.max_retries, 0)
        self.dotenv.assert_called_with(override=False)

    def test_invalid_timeout_and_retries_are_not_replaced_with_defaults(self):
        for value in (0, -1, True, float("inf"), float("nan"), "bad"):
            with self.subTest(timeout=value), self.assertRaises(LLMConfigurationError):
                LLMClient(**SETTINGS, timeout=value)
        for value in (-1, True, 1.5, "1.5", "bad"):
            with self.subTest(retries=value), self.assertRaises(LLMConfigurationError):
                LLMClient(**SETTINGS, max_retries=value)

    def test_invalid_env_numbers_raise_configuration_error(self):
        for name in ("LLM_TIMEOUT", "LLM_MAX_RETRIES"):
            with self.subTest(variable=name), patch.dict(os.environ, {name: "invalid"}):
                with self.assertRaises(LLMConfigurationError):
                    LLMClient(**SETTINGS)

    def test_rejects_invalid_urls_and_does_not_expose_credentials(self):
        for url in ("not-a-url", "ftp://llm.test", "https://", "https://user:secret@llm.test/v1", "https://llm.test:bad/v1", "https://llm.test/v1?api_key=secret"):
            with self.subTest(url=url), self.assertRaises(LLMConfigurationError) as raised:
                LLMClient(**{**SETTINGS, "base_url": url})
            self.assertNotIn("secret", str(raised.exception))
        config = LLMConfig.from_env(**SETTINGS)
        self.assertNotIn(SETTINGS["api_key"], repr(config))
        self.assertEqual(config.timeout, 60)
        self.assertEqual(config.max_retries, 2)
        self.assertIsInstance(LLMConfigurationError("test"), ValueError)
        self.assertIsInstance(LLMConfigurationError("test"), LLMError)

    def test_clients_are_lazy_and_legacy_constructor_is_preserved(self):
        with patch("agent.LLMclient.OpenAI") as sync, patch("agent.LLMclient.AsyncOpenAI") as async_client:
            llm = NovelAgent("test-model", "unit-test-key", "http://localhost:8080/v1", "local", 10, "大纲")
            self.assertIsInstance(llm, LLMClient)
            self.assertEqual(llm.build_target, "大纲")
            self.assertEqual(llm.provider, "local")
            sync.assert_not_called()
            async_client.assert_not_called()


class LLMSyncTests(EnvironmentCase):
    def setUp(self):
        super().setUp()
        self.requests = []
        self.reply = lambda _: httpx.Response(200, json=completion())
        self.sdk = OpenAI(
            api_key=SETTINGS["api_key"], base_url=SETTINGS["base_url"], max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(self.handle)),
        )
        self.addCleanup(self.sdk.close)
        self.constructor = patch("agent.LLMclient.OpenAI", return_value=self.sdk).start()
        self.llm = LLMClient(**SETTINGS, max_retries=0)
        self.addCleanup(self.llm.close)

    def handle(self, request):
        self.requests.append(request)
        return self.reply(request)

    def use_stream(self, source):
        self.reply = lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=source)

    def test_chat_uses_configured_endpoint_and_authorization(self):
        self.assertEqual(self.llm.chat(MESSAGES, temperature=0, max_tokens=100), "海港的灯亮了。")
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://llm.test/v1/chat/completions")
        self.assertEqual(request.headers["authorization"], "Bearer unit-test-key")
        self.assertEqual(json.loads(request.content), {
            "model": "test-model", "messages": MESSAGES, "stream": False, "temperature": 0, "max_tokens": 100,
        })
        self.constructor.assert_called_once_with(**{
            "api_key": SETTINGS["api_key"], "base_url": SETTINGS["base_url"], "timeout": 60.0, "max_retries": 0,
        })

    def test_raw_completion_preserves_usage_and_tool_calls(self):
        tools = [{"type": "function", "function": {"name": "outline", "parameters": {"type": "object"}}}]
        calls = [{"id": "call-1", "type": "function", "function": {"name": "outline", "arguments": "{}"}}]
        self.reply = lambda _: httpx.Response(200, json=completion(None, tool_calls=calls))
        response = self.llm.completion(MESSAGES, tools=tools, extra_body={"custom_option": True})
        self.assertEqual(response.usage.total_tokens, 11)
        self.assertEqual(response.choices[0].message.tool_calls[0].function.name, "outline")
        body = json.loads(self.requests[0].content)
        self.assertEqual(body["tools"], tools)
        self.assertTrue(body["custom_option"])
        self.assertNotIn("temperature", body)
        with self.assertRaises(LLMResponseError):
            self.llm.chat(MESSAGES)

    def test_stream_skips_empty_events_and_other_choices_then_closes(self):
        source = TrackingStream([
            event(), event(choices=[]), event("海港"), event(choices=[
                {"index": 1, "delta": {"content": "不应合并"}, "finish_reason": None},
            ]), event("的灯亮了。"),
        ])
        self.use_stream(source)
        self.assertEqual(list(self.llm.stream(MESSAGES)), ["海港", "的灯亮了。"])
        self.assertTrue(source.closed)
        self.assertTrue(json.loads(self.requests[0].content)["stream"])

    def test_think_collects_stream_without_printing_content(self):
        self.use_stream(TrackingStream([event("你好"), event("世界")]))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(self.llm.think(MESSAGES), "你好世界")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(self.requests[0].content)["temperature"], 0)

    def test_empty_responses_raise_instead_of_returning_none(self):
        self.reply = lambda _: httpx.Response(200, json={**completion(), "choices": []})
        with self.assertRaises(LLMResponseError):
            self.llm.chat(MESSAGES)
        source = TrackingStream([event(), event(choices=[])])
        self.use_stream(source)
        with self.assertRaises(LLMResponseError):
            list(self.llm.stream(MESSAGES))
        self.assertTrue(source.closed)

    def test_stream_can_be_closed_early(self):
        source = TrackingStream([event("第一段"), event("第二段")])
        self.use_stream(source)
        with contextlib.closing(self.llm.stream(MESSAGES)) as fragments:
            self.assertEqual(next(fragments), "第一段")
        self.assertTrue(source.closed)

    def test_stream_failure_after_partial_output_raises_without_replay(self):
        source = TrackingStream([event("第一段")], httpx.ReadError("secret upstream details"))
        self.use_stream(source)
        fragments = self.llm.stream(MESSAGES)
        self.assertEqual(next(fragments), "第一段")
        with self.assertRaises(LLMRequestError) as raised:
            next(fragments)
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(source.closed)

    def test_status_errors_preserve_status_but_not_upstream_body(self):
        for code in (401, 429, 500):
            with self.subTest(status=code):
                self.reply = lambda _, code=code: httpx.Response(code, json={"error": {"message": "secret request body"}})
                with self.assertRaises(LLMRequestError) as raised:
                    self.llm.chat(MESSAGES)
                self.assertEqual(raised.exception.status_code, code)
                self.assertNotIn("secret", str(raised.exception))

    def test_network_errors_are_translated(self):
        for failure in (httpx.ConnectError("secret"), httpx.ReadTimeout("secret")):
            with self.subTest(error=type(failure).__name__):
                def fail(_):
                    raise failure
                self.reply = fail
                with self.assertRaises(LLMRequestError) as raised:
                    self.llm.chat(MESSAGES)
                self.assertIsNone(raised.exception.status_code)
                self.assertNotIn("secret", str(raised.exception))

    def test_invalid_messages_and_parameters_fail_before_network(self):
        for messages in ([], None, 1, "hello", {}, [{}], [{"role": "unknown"}], [{"role": []}]):
            with self.subTest(messages=messages), self.assertRaises(LLMConfigurationError):
                self.llm.chat(messages)
        for temperature in (-1, 3, True, float("nan"), "0.5"):
            with self.subTest(temperature=temperature), self.assertRaises(LLMConfigurationError):
                self.llm.chat(MESSAGES, temperature=temperature)
        for options in ({"stream": True}, {"model": "override"}):
            with self.subTest(options=options), self.assertRaises(LLMConfigurationError):
                self.llm.chat(MESSAGES, **options)
        self.assertEqual(self.requests, [])

    def test_context_manager_closes_client_even_on_error(self):
        with self.assertRaisesRegex(RuntimeError, "test"):
            with self.llm as llm:
                llm.chat(MESSAGES)
                raise RuntimeError("test")
        self.assertTrue(self.sdk.is_closed())
        self.llm.close()


class LLMAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch("agent.LLMclient.load_dotenv").start()
        self.requests = []
        self.reply = lambda _: httpx.Response(200, json=completion())
        self.sdk = AsyncOpenAI(
            api_key=SETTINGS["api_key"], base_url=SETTINGS["base_url"], max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self.handle)),
        )
        self.addAsyncCleanup(self.sdk.close)
        patch("agent.LLMclient.AsyncOpenAI", return_value=self.sdk).start()
        self.sync_constructor = patch("agent.LLMclient.OpenAI").start()
        self.llm = LLMClient(**SETTINGS, max_retries=0)
        self.addAsyncCleanup(self.llm.aclose)

    async def handle(self, request):
        self.requests.append(request)
        return self.reply(request)

    def use_stream(self, source):
        self.reply = lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=source)

    async def test_async_chat_and_completion_preserve_usage(self):
        self.assertEqual(await self.llm.achat(MESSAGES), "海港的灯亮了。")
        response = await self.llm.acompletion(MESSAGES, response_format={"type": "json_object"})
        self.assertEqual(response.usage.total_tokens, 11)
        self.assertEqual(json.loads(self.requests[-1].content)["response_format"], {"type": "json_object"})
        self.sync_constructor.assert_not_called()

    async def test_async_stream_and_athink(self):
        source = AsyncTrackingStream([event(), event(choices=[]), event("第一段"), event("第二段")])
        self.use_stream(source)
        self.assertEqual([part async for part in self.llm.astream(MESSAGES)], ["第一段", "第二段"])
        self.assertTrue(source.closed)
        self.use_stream(AsyncTrackingStream([event("合并"), event("结果")]))
        self.assertEqual(await self.llm.athink(MESSAGES), "合并结果")

    async def test_async_empty_response_raises_and_closes_stream(self):
        self.reply = lambda _: httpx.Response(200, json=completion(None))
        with self.assertRaises(LLMResponseError):
            await self.llm.achat(MESSAGES)
        source = AsyncTrackingStream([event(choices=[])])
        self.use_stream(source)
        with self.assertRaises(LLMResponseError):
            _ = [part async for part in self.llm.astream(MESSAGES)]
        self.assertTrue(source.closed)

    async def test_async_early_exit_closes_stream(self):
        source = AsyncTrackingStream([event("第一段"), event("第二段")])
        self.use_stream(source)
        async with contextlib.aclosing(self.llm.astream(MESSAGES)) as fragments:
            self.assertEqual(await anext(fragments), "第一段")
        self.assertTrue(source.closed)

    async def test_async_stream_error_is_translated_without_retry(self):
        source = AsyncTrackingStream([event("第一段")], httpx.ReadError("secret"))
        self.use_stream(source)
        fragments = self.llm.astream(MESSAGES)
        self.assertEqual(await anext(fragments), "第一段")
        with self.assertRaises(LLMRequestError):
            await anext(fragments)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(source.closed)

    async def test_cancelled_stream_is_closed_and_cancellation_propagates(self):
        source = AsyncTrackingStream([event("第一段")], asyncio.CancelledError())
        self.use_stream(source)
        with self.assertRaises(asyncio.CancelledError):
            _ = [part async for part in self.llm.astream(MESSAGES)]
        self.assertTrue(source.closed)

    async def test_async_request_failure_and_context_cleanup(self):
        self.reply = lambda _: httpx.Response(429, json={"error": {"message": "secret"}})
        with self.assertRaises(LLMRequestError) as raised:
            async with self.llm:
                await self.llm.achat(MESSAGES)
        self.assertEqual(raised.exception.status_code, 429)
        self.assertNotIn("secret", str(raised.exception))
        self.assertTrue(self.sdk.is_closed())
        await self.llm.aclose()


if __name__ == "__main__":
    unittest.main()
