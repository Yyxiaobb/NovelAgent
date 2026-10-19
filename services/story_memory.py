from collections.abc import Iterable
import re


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


def _terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", value.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            terms.update(token[index:index + 2] for index in range(len(token) - 1))
        else:
            terms.add(token)
    return terms


def build_project_memory_context(entries: Iterable, query: str, *, limit: int = 16, max_chars: int = 10000) -> str:
    """Select curated project memories that overlap the current chapter plan."""
    query_terms = _terms(query)
    query_text = query.lower()
    ranked: list[tuple[int, object]] = []
    for entry in entries:
        keywords = [str(value).strip() for value in (entry.keywords or []) if str(value).strip()]
        title = (entry.title or "").strip()
        searchable = " ".join((title, entry.content or "", *keywords))
        overlap = len(query_terms & _terms(searchable))
        score = overlap
        if title and title.lower() in query_text:
            score += 100
        score += sum(80 for keyword in keywords if keyword.lower() in query_text)
        if score:
            ranked.append((score, entry))

    category_labels = {
        "character": "人物",
        "world": "世界设定",
        "thread": "未解线索",
        "timeline": "时间线",
    }
    ranked.sort(key=lambda item: (-item[0], item[1].category, item[1].title))
    lines = [
        f"- [{category_labels.get(entry.category, '资料')}] {entry.title}：{entry.content.strip()}"
        for _, entry in ranked[:limit]
    ]
    if not lines:
        return "当前章节没有匹配到手动整理的长期记忆"
    return "\n".join(lines)[:max_chars]
