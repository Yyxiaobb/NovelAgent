from collections.abc import Iterable


def _value(memory: dict | None, key: str) -> str:
    if not isinstance(memory, dict):
        return ""
    value = (memory or {}).get(key, "")
    return str(value).strip() if value else ""


def build_story_memory(chapters: Iterable, *, max_chars: int = 6000) -> str:
    """Compact chapter memories into a bounded continuity context.

    Recent summaries remain in the normal chapter context. This section keeps
    durable facts (characters, settings, open threads and timeline) from older
    chapters without allowing the prompt to grow with the whole manuscript.
    """
    characters: list[str] = []
    settings: list[str] = []
    threads: list[str] = []
    timeline: list[str] = []
    for chapter in chapters:
        memory = chapter.memory or {}
        label = f"第 {chapter.chapter_number} 章"
        for target, key in (
            (characters, "character_state"),
            (settings, "setting_changes"),
            (threads, "unresolved_threads"),
            (timeline, "timeline"),
        ):
            value = _value(memory, key)
            if value and value != "无":
                target.append(f"{label}：{value}")

    sections = []
    for title, values in (
        ("人物状态", characters),
        ("设定变化", settings),
        ("未解决线索", threads),
        ("时间线", timeline),
    ):
        if values:
            sections.append(f"{title}：\n" + "\n".join(values[-12:]))
    result = "\n\n".join(sections)
    if not result:
        return "暂无跨章节长期记忆"
    return result[:max_chars]
