import unittest
from types import SimpleNamespace

from services.story_memory import build_project_memory_context


def memory(
    category, title, content, keywords=(), *, memory_id=1, status="approved", active=True,
    source_chapter_id=None, origin="manual",
):
    return SimpleNamespace(
        id=memory_id,
        category=category,
        title=title,
        content=content,
        keywords=list(keywords),
        review_status=status,
        is_active=active,
        source_chapter_id=source_chapter_id,
        origin=origin,
    )


class StoryMemoryRetrievalTests(unittest.TestCase):
    def test_exact_title_and_keyword_rank_before_weak_phrase_match(self):
        result = build_project_memory_context([
            memory("world", "王城封锁规则", "城门在日落后关闭", ["王城"], memory_id=1),
            memory("character", "沈砚", "沈砚负责护送信使", ["沈砚", "信使"], memory_id=2),
            memory("thread", "密函来源", "密函来自北境", ["密函"], memory_id=3),
        ], "沈砚护送信使前往北境，追查密函来源")
        lines = result.splitlines()
        self.assertIn("沈砚", lines[0])
        self.assertIn("命中：标题", lines[0])
        self.assertIn("密函来源", result)

    def test_category_hint_and_review_state_filter(self):
        result = build_project_memory_context([
            memory("world", "灵脉规则", "灵脉决定术士的能力上限", ["设定"], memory_id=1),
            memory("character", "待审核人物", "不应进入正文", status="pending", memory_id=2),
            memory("thread", "已停用线索", "不应进入正文", active=False, memory_id=3),
        ], "补充世界设定和能力规则")
        self.assertIn("灵脉规则", result)
        self.assertIn("类别", result)
        self.assertNotIn("待审核人物", result)
        self.assertNotIn("已停用线索", result)

    def test_current_chapter_extracted_memory_is_not_fed_back(self):
        result = build_project_memory_context([
            memory(
                "character", "当前章人物", "刚刚提取的事实", ["人物"],
                source_chapter_id=9, origin="chapter_extract", memory_id=1,
            ),
            memory(
                "character", "前文人物", "已经审核的事实", ["人物"],
                source_chapter_id=8, origin="chapter_extract", memory_id=2,
            ),
        ], "人物状态变化", current_chapter_id=9)
        self.assertNotIn("当前章人物", result)
        self.assertIn("前文人物", result)
        self.assertIn("来源章节", result)


if __name__ == "__main__":
    unittest.main()
