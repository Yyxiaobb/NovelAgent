"""Render a project and its active chapters as portable text documents."""

from models.projects import Chapter, Project


def _chapter_heading(chapter: Chapter) -> str:
    title = (chapter.chaptername or "").strip() or "未命名章节"
    return f"第 {chapter.chapter_number} 章 {title}"


def render_project_export(project: Project, chapters: list[Chapter], file_format: str) -> str:
    """Render the same project content in Markdown or plain text."""
    title = (project.projectname or "").strip() or "未命名作品"
    introduction = (project.introduction or "").strip()
    outline = (project.outline or "").strip()
    project_type = (project.project_type or "").strip()

    if file_format == "markdown":
        sections = [f"# {title}"]
        if project_type:
            sections.append(f"**类型：** {project_type}")
        if introduction:
            sections.extend(("## 作品简介", introduction))
        if outline:
            sections.extend(("## 故事大纲", outline))
        sections.append("## 正文")
        for chapter in chapters:
            sections.extend((f"### {_chapter_heading(chapter)}", (chapter.content or "").strip()))
        return "\n\n".join(sections).rstrip() + "\n"

    sections = [title]
    if project_type:
        sections.extend((f"作品类型：{project_type}",))
    if introduction:
        sections.extend(("作品简介", introduction))
    if outline:
        sections.extend(("故事大纲", outline))
    sections.append("正文")
    for chapter in chapters:
        sections.extend((_chapter_heading(chapter), (chapter.content or "").strip()))
    return "\n\n".join(sections).rstrip() + "\n"
