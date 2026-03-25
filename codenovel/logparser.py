"""Parse real Codex CLI terminal logs into structured RenderedLine entries."""
from __future__ import annotations

import re
from pathlib import Path

from codenovel.simulator import RenderedLine


def _is_cjk_start(text: str) -> bool:
    if not text:
        return False
    cp = ord(text[0])
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x2E80 <= cp <= 0x2FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0xFE30 <= cp <= 0xFE4F
        or 0x20000 <= cp <= 0x2A6DF
        or 0x3000 <= cp <= 0x303F
        or 0xFF00 <= cp <= 0xFFEF
    )


_DIFF_MOD = re.compile(r"^\s{4,}(\d+)\s([+-])\S")
_DIFF_CTX = re.compile(r"^\s{4,}(\d+)\s{2}\S")

_SKIP_PREFIXES = (
    "Windows PowerShell",
    "版权所有",
    "安装最新的",
    "(base) PS ",
    "PS ",
    "加载个人",
)


def parse_codex_log(text: str) -> list[RenderedLine]:
    raw_lines = text.splitlines()

    start = 0
    for i, raw in enumerate(raw_lines):
        if raw.strip().startswith("╭"):
            start = i
            break

    result: list[RenderedLine] = []

    for raw in raw_lines[start:]:
        stripped = raw.strip()
        if not stripped:
            continue

        if any(stripped.startswith(p) for p in _SKIP_PREFIXES):
            continue

        if stripped[0] in "╭╰":
            result.append(RenderedLine("header_box", stripped))
            continue
        if stripped.startswith("│"):
            result.append(RenderedLine("header_box", stripped))
            continue

        if stripped.startswith("❯"):
            result.append(RenderedLine("user_prompt", stripped[1:].strip()))
            continue

        if stripped[0] == "─" and len(stripped) > 20:
            m = re.search(r"Worked for\s+(.+?)[\s─]*$", stripped)
            if m:
                result.append(RenderedLine("work_timer", f"Worked for {m.group(1).strip()}"))
            else:
                result.append(RenderedLine("separator", ""))
            continue

        if stripped.startswith("■"):
            result.append(RenderedLine("interrupted", stripped[1:].strip()))
            continue

        if stripped.startswith("⚠"):
            result.append(RenderedLine("warning", stripped[1:].strip()))
            continue

        if stripped.startswith("Tip:") or stripped.startswith("tip:"):
            result.append(RenderedLine("tip", stripped))
            continue

        if stripped.startswith("• "):
            body = stripped[2:]
            if body.startswith("Ran "):
                result.append(RenderedLine("command_run", body[4:]))
            elif body.startswith("Waited"):
                result.append(RenderedLine("waited", body))
            elif body.startswith("Edited"):
                result.append(RenderedLine("edited", body))
            elif _is_cjk_start(body):
                result.append(RenderedLine("commentary", body))
            else:
                result.append(RenderedLine("thinking", body))
            continue

        if stripped.startswith("└"):
            result.append(RenderedLine("command_output", stripped[1:].strip()))
            continue

        m_diff = _DIFF_MOD.match(raw)
        if m_diff:
            kind = "diff_add" if m_diff.group(2) == "+" else "diff_del"
            result.append(RenderedLine(kind, stripped))
            continue

        if _DIFF_CTX.match(raw):
            result.append(RenderedLine("diff_ctx", stripped))
            continue

        if stripped == "⋮" or stripped.startswith("… +"):
            result.append(RenderedLine("child_deep", stripped))
            continue

        if raw.startswith("  "):
            result.append(RenderedLine("child_deep", stripped))
            continue

        result.append(RenderedLine("plain", stripped))

    return result


_GROUP_STARTERS = frozenset({
    "user_prompt", "separator", "work_timer", "interrupted",
    "header_box", "command_run", "edited", "commentary",
    "thinking", "warning", "tip",
})


def group_parsed_lines(lines: list[RenderedLine]) -> list[list[RenderedLine]]:
    groups: list[list[RenderedLine]] = []
    current: list[RenderedLine] = []

    for line in lines:
        if line.kind in _GROUP_STARTERS and current:
            groups.append(current)
            current = []
        current.append(line)

    if current:
        groups.append(current)

    return groups


def load_and_parse(path: Path) -> tuple[list[RenderedLine], list[list[RenderedLine]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = parse_codex_log(text)
    groups = group_parsed_lines(lines)
    return lines, groups
