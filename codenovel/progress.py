from __future__ import annotations

import json
from pathlib import Path


DEFAULT_PROGRESS_PATH = Path.home() / ".codenovel" / "progress.json"


class BookProgressStore:
    """Persist per-book reading position using original TXT line numbers."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PROGRESS_PATH

    def load(self, book_path: Path) -> int | None:
        data = self._read()
        key = str(book_path.expanduser().resolve())
        record = data.get("books", {}).get(key)
        if not isinstance(record, dict):
            return None
        line = record.get("line")
        if isinstance(line, int) and line >= 1:
            return line
        return None

    def save(self, book_path: Path, line_number: int) -> None:
        if line_number < 1:
            line_number = 1

        data = self._read()
        books = data.setdefault("books", {})
        books[str(book_path.expanduser().resolve())] = {"line": line_number}

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"version": 1, "books": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "books": {}}
        if not isinstance(data, dict):
            return {"version": 1, "books": {}}
        books = data.get("books")
        if not isinstance(books, dict):
            data["books"] = {}
        data.setdefault("version", 1)
        return data
