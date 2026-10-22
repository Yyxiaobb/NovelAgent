# Agent 模型客户端

`LLMclient.py` 为 Agent 提供第三方模型接入层，适用于支持 OpenAI Chat Completions 协议的服务。不包含 Agent 工作流或新的 HTTP 路由，也不会自动转换其他供应商的原生协议。

## 配置

长篇章节正文任务通过 Redis + ARQ 在独立进程中执行。安装后端依赖时会一并安装 ARQ：

```powershell
python -m pip install -r requirements-dev.txt
```

在项目根目录 `.env` 配置 Redis 地址：

```dotenv
REDIS_URL=redis://localhost:6379/0
```

本地启动 Redis 后，分别启动 API 和 Worker；Worker 命令从项目根目录运行：

```powershell
python -m arq workers.generation.WorkerSettings
```

任务记录仍保存在数据库中，Worker 启动时会把未完成任务重新放入队列。队列短暂不可用时，新任务会明确失败并可在 Redis 恢复后重试。

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

## 知识库与 RAG 配置

用户知识库会将 TXT / Markdown 文档切分并调用 OpenAI-compatible Embeddings 接口建立向量索引。可在 `.env` 单独配置向量服务：

```dotenv
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_API_KEY=your-embedding-api-key
RAG_EMBEDDING_BASE_URL=https://your-embedding-provider.example/v1
```

如果未设置 `RAG_EMBEDDING_API_KEY` 和 `RAG_EMBEDDING_BASE_URL`，系统会依次尝试复用 `LLM_API_KEY` / `API_KEY` 与 `LLM_BASE_URL` / `BASE_URL`。只有当前模型供应商提供兼容的 `/embeddings` 接口，并支持 `RAG_EMBEDDING_MODEL` 指定的模型时才能直接复用；否则需要单独申请 Embedding 服务的 API Key。

当前版本将向量以 JSON 保存在应用数据库，并在应用层计算相似度，适合个人和小规模知识库。文档数量和片段量明显增长后，建议迁移到 pgvector、Qdrant 或 Milvus。后台索引目前使用 FastAPI `BackgroundTasks`，服务重启会中断正在执行的索引，可在知识库页面点击“重试”。

后端的智能体路由 `POST /api/agent/project-field` 使用该客户端为作品名称、作品简介或作品类型生成候选内容，需要登录并先配置上述模型环境变量。

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
