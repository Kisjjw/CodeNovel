from __future__ import annotations

from pathlib import Path


PLACEHOLDER_TEXT = """
No TXT novel loaded.

Usage:
  codenovel path\\to\\novel.txt

Tips:
  - The center pane is intentionally dim so it reads like inactive terminal output.
  - Press space to pause the fake activity before turning a page.
  - Press j/k or PageDown/PageUp to move through the TXT file.
""".strip()


def load_book_text(book_path: Path | None) -> str:
    if book_path is None:
        return PLACEHOLDER_TEXT
    if not book_path.exists():
        return f"TXT file not found:\n{book_path}"
    if book_path.suffix.lower() != ".txt":
        return f"Only .txt files are supported right now.\n\nProvided:\n{book_path.name}"
    try:
        return book_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return book_path.read_text(encoding="gb18030", errors="replace")


def style_book_text(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    if not lines:
        return PLACEHOLDER_TEXT
    return "\n".join(f"  {line if line else ' '}" for line in lines)


def split_book_lines(content: str) -> list[str]:
    lines = [line.rstrip() for line in content.splitlines()]
    if not lines:
        lines = PLACEHOLDER_TEXT.splitlines()
    return [f"  {line}" for line in lines if line]
