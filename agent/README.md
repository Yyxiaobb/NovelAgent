# Agent 模型客户端

`LLMclient.py` 为 Agent 提供第三方模型接入层，适用于支持 OpenAI Chat Completions 协议的服务。不包含 Agent 工作流或新的 HTTP 路由，也不会自动转换其他供应商的原生协议。

## 配置

安装接入层依赖：

```powershell
python -m pip install -r agent/requirements.txt
```

在项目根目录的 `.env` 中添加以下配置，模型名称、密钥和服务地址以供应商提供的信息为准；地址通常包含 `/v1`，不要填写到 `/chat/completions`：

```dotenv
LLM_MODEL=your-model-id
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_PROVIDER=your-provider
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
```

`model`、`api_key`、`base_url` 必填。`provider` 仅是服务标识，不决定 URL 或协议。HTTP 地址可用于本地兼容服务，公网服务建议使用 HTTPS。`.env` 不应提交到 Git。

构造参数优先于环境变量；环境变量优先于 `.env` 中的同名变量。保留旧配置 `MODEL`、`API_KEY`、`BASE_URL`、`PROVIDER`、`TIMEOUT` 和 `MAX_RETRIES`，但优先读取 `LLM_` 前缀的配置。超时单位为秒，重试使用 SDK 自带机制。

## 同步调用

```python
from agent import LLMClient, LLMRequestError

messages = [
    {"role": "system", "content": "你是一位小说创作助手。"},
    {"role": "user", "content": "为一座海港城市构思三个故事开场。"},
]

try:
    with LLMClient() as llm:
        text = llm.chat(messages, temperature=0.7, max_tokens=500)
        for fragment in llm.stream(messages):
            # 将片段发送给终端、前端事件流或工作流，不由接入层直接打印。
            pass
except LLMRequestError as error:
    # error.status_code 可用于识别 401、429 等；网络错误为 None。
    pass
```

## 异步调用（FastAPI / Agent 工作流）

```python
from contextlib import aclosing
from agent import LLMClient

async def write_chapter(messages):
    async with LLMClient() as llm:
        return await llm.achat(messages)

async def stream_chapter(messages):
    async with LLMClient() as llm:
        async with aclosing(llm.astream(messages)) as fragments:
            async for fragment in fragments:
                yield fragment
```

使用同步生成器提前退出时，通过 `contextlib.closing(llm.stream(...))` 明确关闭；异步使用 `aclosing`。完整消费、关闭生成器、流中异常或取消时，接入层会关闭该响应流。客户端支持复用；同步资源用 `close()` 释放，异步资源用 `await aclose()` 释放，同一实例混用时两者都需调用。

## 原始响应与兼容接口

- `completion()` / `acompletion()` 返回 SDK 的 `ChatCompletion`，保留 `usage`、`finish_reason`、`tool_calls` 等字段。工具调用和 JSON 格式等参数通过 `tools`、`response_format`、`extra_body` 传入，具体能力取决于供应商。
- `chat()` / `achat()` 返回第一个候选的文本；`stream()` / `astream()` 仅输出第一个候选的正文片段，不输出推理字段或工具参数增量。工具调用请使用原始非流式接口。
- `NovelAgent` 类名、原有构造参数及 `think(messages, temperature=0)` 保留；`think()` 收集流式文本并返回字符串，新增对应的 `athink()`。不再自动打印正文，也不再吞掉异常返回 `None`，调用方应捕获 `LLMError`。
- `LLMConfigurationError` 表示配置或参数无效；`LLMRequestError` 表示超时、网络或服务错误；`LLMResponseError` 表示缺少预期文本。已输出部分内容后若流失败，会继续抛错，不把半段内容当作完整结果，也不自动重放流。
- 新接口默认不发送 `temperature`，避免强制指定不兼容的采样参数。`max_tokens` / `max_completion_tokens` 等参数请根据服务支持情况传入。

测试使用 `httpx.MockTransport` 驱动真实 SDK 的序列化与 SSE 解析，不使用真实密钥、不发出模型网络请求：

```powershell
python -B -m unittest discover -s tests -p test_llm_client.py -v
```
