"""Bounded single-agent Function Calling runtime with project-scoped read tools."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from crud import projects, story_memory as story_memory_crud
from services.story_memory import build_project_memory_context
from utils.generation_telemetry import log_generation_metric


MAX_MODEL_ROUNDS = 5
MAX_TOOL_CALLS = 8
MAX_TOOL_RESULT_CHARS = 6000


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SearchArgs(_Args):
    query: str = Field(min_length=1, max_length=500)


TOOL_DEFINITIONS = [
    {"type": "function", "function": {
        "name": "get_project_context", "description": "读取当前作品名称、类型、简介和大纲。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "list_chapters", "description": "读取当前作品的章节目录，最多返回 100 章。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    }},
    {"type": "function", "function": {
        "name": "search_story_memory", "description": "检索当前作品已审核通过的长期记忆。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
        }, "required": ["query"], "additionalProperties": False},
    }},
]


async def _execute(name: str, raw_arguments: str, db: AsyncSession, *, project_id: int, user_id: int) -> str:
    try:
        args = json.loads(raw_arguments or "{}")
    except (TypeError, json.JSONDecodeError):
        return json.dumps({"error": "工具参数不是有效 JSON"}, ensure_ascii=False)
    if name == "get_project_context":
        if not isinstance(args, dict) or args:
            return json.dumps({"error": "参数无效"}, ensure_ascii=False)
        project = await projects.get_project(db, project_id, user_id)
        if project is None:
            return json.dumps({"error": "作品不可访问"}, ensure_ascii=False)
        result = {"projectname": project.projectname, "project_type": project.project_type,
                  "introduction": project.introduction, "outline": project.outline}
    elif name == "list_chapters":
        if not isinstance(args, dict) or args:
            return json.dumps({"error": "参数无效"}, ensure_ascii=False)
        chapters = await projects.get_project_chapters(db, project_id, user_id)
        if chapters is None:
            return json.dumps({"error": "作品不可访问"}, ensure_ascii=False)
        result = [{"chapter_number": item.chapter_number, "chaptername": item.chaptername,
                   "has_plan": bool(item.plan), "has_content": bool(item.content)} for item in chapters[:100]]
    elif name == "search_story_memory":
        try:
            query = _SearchArgs.model_validate(args).query
        except ValidationError:
            return json.dumps({"error": "参数无效，query 必须为 1 至 500 个字符"}, ensure_ascii=False)
        if await projects.get_project(db, project_id, user_id) is None:
            return json.dumps({"error": "作品不可访问"}, ensure_ascii=False)
        entries = await story_memory_crud.list_active_project_memories(db, project_id)
        result = build_project_memory_context(entries, query, limit=8, max_chars=MAX_TOOL_RESULT_CHARS)
    else:
        return json.dumps({"error": "未知工具"}, ensure_ascii=False)
    rendered = json.dumps(result, ensure_ascii=False, default=str)
    return rendered[:MAX_TOOL_RESULT_CHARS]


async def run_agent(client: Any, messages: list[dict[str, Any]], db: AsyncSession, *, project_id: int,
                    user_id: int, max_tokens: int, temperature: float = 0.3) -> str:
    """Run the model/tool loop. Read tools are always bound to the authenticated project."""
    conversation = list(messages)
    total_calls = 0
    total_prompt_chars = sum(
        len(str(message.get("content") or "")) for message in conversation
    )
    agent_started = perf_counter()
    for round_number in range(1, MAX_MODEL_ROUNDS + 1):
        round_started = perf_counter()
        response = await client.acompletion(conversation, tools=TOOL_DEFINITIONS, tool_choice="auto",
                                            temperature=temperature, max_tokens=max_tokens)
        if not response.choices:
            raise ValueError("model returned no choices")
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        usage = getattr(response, "usage", None)
        log_generation_metric(
            "agent_round", "function_calling", (perf_counter() - round_started) * 1000,
            round=round_number, tool_calls=len(tool_calls),
            input_chars=sum(len(str(item.get("content") or "")) for item in conversation),
            output_chars=len(message.content) if isinstance(message.content, str) else 0,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )
        if not tool_calls:
            if not isinstance(message.content, str) or not message.content.strip():
                raise ValueError("model returned no text")
            log_generation_metric(
                "agent_complete", "function_calling", (perf_counter() - agent_started) * 1000,
                rounds=round_number, tool_calls=total_calls,
                initial_input_chars=total_prompt_chars, output_chars=len(message.content),
            )
            return message.content.strip()
        conversation.append({"role": "assistant", "content": message.content, "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.function.name,
             "arguments": call.function.arguments}} for call in tool_calls
        ]})
        for call in tool_calls:
            total_calls += 1
            if total_calls > MAX_TOOL_CALLS:
                raise ValueError("agent tool-call limit reached")
            output = await _execute(call.function.name, call.function.arguments, db,
                                    project_id=project_id, user_id=user_id)
            conversation.append({"role": "tool", "tool_call_id": call.id, "content": output})
    raise ValueError("agent model-round limit reached")
