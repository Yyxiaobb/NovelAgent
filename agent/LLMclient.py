"""面向 OpenAI Chat Completions 兼容服务的同步、异步模型客户端。"""

from __future__ import annotations

import math
import os
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from httpx import HTTPError, TimeoutException
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAI,
    OpenAIError,
)
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam


__all__ = [
    "LLMClient", "LLMConfig", "LLMError", "LLMConfigurationError",
    "LLMRequestError", "LLMResponseError", "NovelAgent",
]


class LLMError(RuntimeError):
    """模型调用的统一异常基类。"""


class LLMConfigurationError(LLMError, ValueError):
    """缺少配置，或调用参数不合法。"""


class LLMRequestError(LLMError):
    """第三方服务请求失败；status_code 可用于区分鉴权、限流等错误。"""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LLMResponseError(LLMError):
    """服务返回了无法作为文本使用的响应。"""


def _env(name: str, legacy: str, default: Any = None) -> Any:
    for key in (name, legacy):
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return default


@dataclass(frozen=True)
class LLMConfig:
    model: str
    api_key: str = field(repr=False)
    base_url: str
    provider: str = "openai-compatible"
    timeout: float = 60.0
    max_retries: int = 2

    def __post_init__(self):
        for name in ("model", "api_key", "base_url", "provider"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LLMConfigurationError(f"必须配置有效的 {name}，可通过构造参数或 .env 提供")
            object.__setattr__(self, name, value.strip())
        try:
            parsed = urlsplit(self.base_url)
            valid_url = parsed.scheme in ("http", "https") and bool(parsed.hostname)
            valid_url = valid_url and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
            parsed.port  # 同时检查非法端口。
        except ValueError:
            valid_url = False
        if not valid_url:
            raise LLMConfigurationError("base_url 必须为不含账号、查询参数或片段的 HTTP(S) 服务地址")
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)):
            raise LLMConfigurationError("timeout 必须为大于 0 的有限秒数")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise LLMConfigurationError("timeout 必须为大于 0 的有限秒数")
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise LLMConfigurationError("max_retries 必须为非负整数")

    @classmethod
    def from_env(
        cls, *, model: str | None = None, api_key: str | None = None,
        base_url: str | None = None, provider: str | None = None,
        timeout: float | None = None, max_retries: int | None = None,
    ) -> LLMConfig:
        # 显式参数 > 进程环境变量 > .env；导入模块时不修改进程环境。
        load_dotenv(override=False)
        timeout_value = timeout if timeout is not None else _env("LLM_TIMEOUT", "TIMEOUT", "60")
        retries_value = max_retries if max_retries is not None else _env("LLM_MAX_RETRIES", "MAX_RETRIES", "2")
        try:
            parsed_timeout = float(timeout_value)
            parsed_retries = int(retries_value) if isinstance(retries_value, str) else retries_value
        except (TypeError, ValueError, OverflowError):
            raise LLMConfigurationError("timeout 必须为正数，max_retries 必须为非负整数") from None
        if isinstance(timeout_value, bool):
            raise LLMConfigurationError("timeout 必须为大于 0 的有限秒数")
        return cls(
            model=model if model is not None else _env("LLM_MODEL", "MODEL"),
            api_key=api_key if api_key is not None else _env("LLM_API_KEY", "API_KEY"),
            base_url=base_url if base_url is not None else _env("LLM_BASE_URL", "BASE_URL"),
            provider=provider if provider is not None else _env("LLM_PROVIDER", "PROVIDER", "openai-compatible"),
            timeout=parsed_timeout,
            max_retries=parsed_retries,
        )


def _request_error(error: OpenAIError | HTTPError) -> LLMRequestError:
    # 不拼接供应商错误正文，以免把密钥、提示词或小说内容写入应用日志。
    if isinstance(error, (APITimeoutError, TimeoutException)):
        return LLMRequestError("模型服务请求超时，请稍后重试")
    if isinstance(error, (APIConnectionError, HTTPError)):
        return LLMRequestError("无法连接模型服务，请检查服务地址或网络")
    if isinstance(error, APIStatusError):
        return LLMRequestError(f"模型服务请求失败（HTTP {error.status_code}）", error.status_code)
    return LLMRequestError("模型服务调用失败")


class LLMClient:
    """连接 OpenAI 兼容服务。provider 仅作标识，不自动切换原生供应商协议。

    chat/achat 返回文本，stream/astream 输出文本片段；completion/acompletion
    保留工具调用、用量、结束原因等原始响应。SDK 负责请求重试，不重试已输出的流。
    同步用 with，异步用 async with；混用时分别调用 close 和 aclose。
    """

    def __init__(
        self, model: str | None = None, api_key: str | None = None,
        base_url: str | None = None, provider: str | None = None,
        timeout: float | None = None, build_target: str | None = None,
        *, max_retries: int | None = None,
    ):
        self.config = LLMConfig.from_env(
            model=model, api_key=api_key, base_url=base_url, provider=provider,
            timeout=timeout, max_retries=max_retries,
        )
        self.model = self.config.model
        self.provider = self.config.provider
        self.build_target = build_target
        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    def _client_options(self) -> dict[str, Any]:
        return {
            "api_key": self.config.api_key, "base_url": self.config.base_url,
            "timeout": self.config.timeout, "max_retries": self.config.max_retries,
        }

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(**self._client_options())
        return self._client

    @property
    def async_client(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI(**self._client_options())
        return self._async_client

    def _params(
        self, messages: Sequence[ChatCompletionMessageParam], *, stream: bool,
        temperature: float | None, options: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)) or not messages:
            raise LLMConfigurationError("messages 必须是非空消息列表")
        roles = {"system", "developer", "user", "assistant", "tool", "function"}
        if any(
            not isinstance(message, Mapping)
            or not isinstance(message.get("role"), str)
            or message["role"] not in roles
            for message in messages
        ):
            raise LLMConfigurationError("每条消息必须包含有效的 role")
        if {"model", "stream", "messages"}.intersection(options):
            raise LLMConfigurationError("model、stream 和 messages 由客户端接口管理，不能重复传入")
        params = {"model": self.model, "messages": list(messages), "stream": stream, **options}
        if temperature is not None:
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
                raise LLMConfigurationError("temperature 必须为 0 到 2 之间的有限数值")
            if not math.isfinite(temperature) or not 0 <= temperature <= 2:
                raise LLMConfigurationError("temperature 必须为 0 到 2 之间的有限数值")
            params["temperature"] = temperature
        return params

    def completion(
        self, messages: Sequence[ChatCompletionMessageParam], *,
        temperature: float | None = None, **options: Any,
    ) -> ChatCompletion:
        """返回原始非流式响应；可传 tools、response_format、extra_body 等 SDK 参数。"""
        params = self._params(messages, stream=False, temperature=temperature, options=options)
        try:
            return self.client.chat.completions.create(**params)
        except (OpenAIError, HTTPError) as error:
            raise _request_error(error) from error

    async def acompletion(
        self, messages: Sequence[ChatCompletionMessageParam], *,
        temperature: float | None = None, **options: Any,
    ) -> ChatCompletion:
        params = self._params(messages, stream=False, temperature=temperature, options=options)
        try:
            return await self.async_client.chat.completions.create(**params)
        except (OpenAIError, HTTPError) as error:
            raise _request_error(error) from error

    @staticmethod
    def _text(response: ChatCompletion) -> str:
        if response.choices and isinstance(response.choices[0].message.content, str):
            return response.choices[0].message.content
        raise LLMResponseError("模型未返回文本；工具调用等结构化结果请使用 completion/acompletion")

    def chat(self, messages: Sequence[ChatCompletionMessageParam], **options: Any) -> str:
        return self._text(self.completion(messages, **options))

    async def achat(self, messages: Sequence[ChatCompletionMessageParam], **options: Any) -> str:
        return self._text(await self.acompletion(messages, **options))

    def stream(
        self, messages: Sequence[ChatCompletionMessageParam], *,
        temperature: float | None = None, **options: Any,
    ) -> Iterator[str]:
        params = self._params(messages, stream=True, temperature=temperature, options=options)
        response = None
        has_content = False
        try:
            response = self.client.chat.completions.create(**params)
            for chunk in response:
                for choice in chunk.choices:
                    content = choice.delta.content
                    if choice.index == 0 and isinstance(content, str) and content:
                        has_content = True
                        yield content
            if not has_content:
                raise LLMResponseError("模型流式响应中没有文本内容")
        except (OpenAIError, HTTPError) as error:
            raise _request_error(error) from error
        finally:
            if response is not None:
                response.close()

    async def astream(
        self, messages: Sequence[ChatCompletionMessageParam], *,
        temperature: float | None = None, **options: Any,
    ) -> AsyncIterator[str]:
        params = self._params(messages, stream=True, temperature=temperature, options=options)
        response = None
        has_content = False
        try:
            response = await self.async_client.chat.completions.create(**params)
            async for chunk in response:
                for choice in chunk.choices:
                    content = choice.delta.content
                    if choice.index == 0 and isinstance(content, str) and content:
                        has_content = True
                        yield content
            if not has_content:
                raise LLMResponseError("模型流式响应中没有文本内容")
        except (OpenAIError, HTTPError) as error:
            raise _request_error(error) from error
        finally:
            if response is not None:
                await response.close()

    def think(
        self, messages: Sequence[ChatCompletionMessageParam], temperature: float = 0, **options: Any,
    ) -> str:
        """兼容原接口：收集流式文本后返回，不向标准输出打印创作内容。"""
        return "".join(self.stream(messages, temperature=temperature, **options))

    async def athink(
        self, messages: Sequence[ChatCompletionMessageParam], temperature: float = 0, **options: Any,
    ) -> str:
        return "".join([text async for text in self.astream(messages, temperature=temperature, **options)])

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


class NovelAgent(LLMClient):
    """保留现有类名；新的 Agent 可直接组合使用 LLMClient。"""
