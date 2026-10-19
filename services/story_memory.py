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


def _phrases(value: str) -> set[str]:
    """Return short Chinese phrases and normalized word sequences for matching."""
    phrases: set[str] = set()
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", value.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            phrases.update(token[index:index + size] for size in (2, 3, 4) for index in range(len(token) - size + 1))
        else:
            phrases.add(token)
    return phrases


def _category_hints(query: str) -> dict[str, set[str]]:
    return {
        "character": _terms("人物 角色 主角 配角 性格 身份") & _terms(query),
        "world": _terms("世界 设定 规则 地理 势力 能力") & _terms(query),
        "thread": _terms("线索 秘密 谜团 真相 伏笔") & _terms(query),
        "timeline": _terms("时间 日期 过去 未来 当天") & _terms(query),
    }


def build_project_memory_context(
    entries: Iterable,
    query: str,
    *,
    limit: int = 16,
    max_chars: int = 10000,
    current_chapter_id: int | None = None,
) -> str:
    """Select approved memories with hybrid phrase, keyword and category scoring."""
    query_terms = _terms(query)
    query_phrases = _phrases(query)
    query_text = query.lower()
    category_hints = _category_hints(query)
    ranked: list[tuple[int, object, list[str]]] = []
    for entry in entries:
        if getattr(entry, "review_status", "approved") != "approved" or not getattr(entry, "is_active", True):
            continue
        source_chapter_id = getattr(entry, "source_chapter_id", None)
        if (
            current_chapter_id is not None
            and source_chapter_id == current_chapter_id
            and getattr(entry, "origin", "manual") == "chapter_extract"
        ):
            # Do not feed facts extracted from the chapter being written back
            # into that chapter's own prompt.
            continue
        keywords = [str(value).strip() for value in (entry.keywords or []) if str(value).strip()]
        title = (entry.title or "").strip()
        searchable = " ".join((title, entry.content or "", *keywords))
        searchable_terms = _terms(searchable)
        searchable_phrases = _phrases(searchable)
        overlap = len(query_terms & searchable_terms)
        phrase_overlap = len(query_phrases & searchable_phrases)
        reasons: list[str] = []
        score = overlap + phrase_overlap * 3
        if overlap:
            reasons.append("词语")
        if phrase_overlap:
            reasons.append("短语")
        if title and title.lower() in query_text:
            score += 100
            reasons.append("标题")
        keyword_hits = [keyword for keyword in keywords if keyword.lower() in query_text]
        if keyword_hits:
            score += 80 * len(keyword_hits)
            reasons.append("关键词")
        category_hits = category_hints.get(entry.category, set())
        if category_hits:
            score += 12
            reasons.append("类别")
        if source_chapter_id is not None:
            score += 2
            reasons.append("来源章节")
        if score:
            reason_order = {"标题": 0, "关键词": 1, "短语": 2, "词语": 3, "类别": 4, "来源章节": 5}
            reasons.sort(key=lambda reason: reason_order[reason])
            ranked.append((score, entry, reasons))

    category_labels = {
        "character": "人物",
        "world": "世界设定",
        "thread": "未解线索",
        "timeline": "时间线",
    }
    ranked.sort(key=lambda item: (-item[0], item[1].category, item[1].title, item[1].id))
    lines = [
        f"- [{category_labels.get(entry.category, '资料')}] {entry.title}（命中：{'、'.join(reasons)}）：{entry.content.strip()}"
        for _, entry, reasons in ranked[:limit]
    ]
    if not lines:
        return "当前章节没有匹配到手动整理的长期记忆"
    return "\n".join(lines)[:max_chars]


def find_memory_conflicts(entries: Iterable, *, threshold: float = 0.35) -> list[dict]:
    """Find likely duplicate or conflicting facts within one memory category."""
    items = list(entries)
    conflicts: list[dict] = []
    for index, first in enumerate(items):
        if getattr(first, "merged_into_id", None) is not None:
            continue
        first_title = (first.title or "").strip().lower()
        first_terms = _terms(" ".join((first.title or "", first.content or "")))
        first_keywords = {str(value).strip().lower() for value in (first.keywords or []) if str(value).strip()}
        for second in items[index + 1:]:
            if getattr(second, "merged_into_id", None) is not None:
                continue
            if first.category != second.category:
                continue
            second_title = (second.title or "").strip().lower()
            second_terms = _terms(" ".join((second.title or "", second.content or "")))
            second_keywords = {str(value).strip().lower() for value in (second.keywords or []) if str(value).strip()}
            reason = None
            similarity = 0.0
            if first_title and first_title == second_title:
                reason, similarity = "same_title", 1.0
            elif first_keywords & second_keywords:
                reason, similarity = "shared_keywords", 0.7
            else:
                union = first_terms | second_terms
                overlap = first_terms & second_terms
                similarity = len(overlap) / len(union) if union else 0.0
                if similarity >= threshold:
                    reason = "similar_content"
            if reason:
                conflicts.append({
                    "first_id": first.id,
                    "second_id": second.id,
                    "category": first.category,
                    "similarity": round(similarity, 3),
                    "reason": reason,
                })
    return sorted(conflicts, key=lambda item: (-item["similarity"], item["first_id"], item["second_id"]))
