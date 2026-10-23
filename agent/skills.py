"""Loader for bundled, trusted Markdown skills (skills are instructions, never code)."""

from dataclasses import dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).with_name("skills")
MAX_SKILL_CHARS = 6000


@dataclass(frozen=True)
class Skill:
    name: str
    version: str
    task_types: tuple[str, ...]
    instructions: str


def load_skill(name: str, *, task_type: str) -> Skill:
    """Load only a named file directly under the bundled skills directory."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("invalid skill name")
    path = (SKILL_ROOT / f"{name}.md").resolve()
    if path.parent != SKILL_ROOT.resolve() or not path.is_file():
        raise ValueError("skill not found")
    text = path.read_text(encoding="utf-8")
    if len(text) > MAX_SKILL_CHARS:
        raise ValueError("skill is too large")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("invalid skill metadata")
    metadata = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    task_types = tuple(item.strip() for item in metadata.get("task_types", "").split(",") if item.strip())
    if metadata.get("name") != name or not metadata.get("version") or task_type not in task_types:
        raise ValueError("skill is not available for this task")
    return Skill(name, metadata["version"], task_types, parts[2].strip())
