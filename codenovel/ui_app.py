from __future__ import annotations

import re
from math import ceil
from pathlib import Path
from random import randint, random
from time import monotonic

from rich.cells import cell_len
from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.scrollbar import ScrollBarRender
from textual.widgets import Static

from codenovel.reader import load_book_text, split_book_lines
from codenovel.simulator import FakeLogEngine, RenderedLine, ReplayEngine

VISIBLE_BOOK_LINES = 3
SCROLL_STEP = 1
INITIAL_BOOK_BATCH = 240
BACKGROUND_BOOK_BATCH = 360
BOOK_LOOKAHEAD_LINES = 96
READER_TEXT_COLOR = "#666666"
READER_HIGHLIGHT_TEXT_COLOR = "#FFFFFF"
READER_LABEL_COLOR = "#8A8A8A"
READER_HIGHLIGHT_PROBABILITY = 0.4
READER_HIGHLIGHT_STREAK_PROBABILITY = 0.45
READER_MIN_GRAY_GAP = 2

_DIFF_LINE_RE = re.compile(r"^(?:(\d+)\s+)?([+\- ])\s?(.*)$")
_DIFF_BLANK_RE = re.compile(r"^(\d+)$")
_DIFF_STATS_RE = re.compile(r"\(\+(\d+)\s-(\d+)\)")
_PATH_SUMMARY_RE = re.compile(r"^(.*?)(\s+\(\+\d+\s-\d+\))$")
_CODE_COMMENT_RE = re.compile(r"//.*$|#.*$")
_CODE_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_CODE_NUMBER_RE = re.compile(r"\b\d+(?:_\d+)*(?:\.\d+)?\b")
_CODE_MACRO_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*!")
_CODE_FUNCTION_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\()")
_CODE_TYPE_RE = re.compile(
    r"\b(?:"
    r"[A-Z][A-Za-z0-9_]*|"
    r"i8|i16|i32|i64|i128|isize|"
    r"u8|u16|u32|u64|u128|usize|"
    r"bool|str|String|Vec|Option|Result"
    r")\b"
)
_CODE_KEYWORD_RE = re.compile(
    r"\b(?:"
    r"async|await|break|class|const|crate|def|elif|else|enum|except|false|finally|"
    r"fn|for|from|if|impl|import|in|let|match|mod|mut|None|Ok|Err|pub|raise|return|"
    r"self|Self|Some|static|struct|super|true|try|use|where|while|with|yield"
    r")\b"
)


def wrap_line(line: str, width: int) -> list[str]:
    """Wrap a single line into multiple visual rows, CJK-aware."""
    if cell_len(line) <= width:
        return [line]
    result: list[str] = []
    current = ""
    for char in line:
        test = current + char
        if cell_len(test) > width:
            result.append(current)
            current = "    " + char
        else:
            current = test
    if current:
        result.append(current)
    return result

BASE_CSS = """
Screen {
    background: black;
    color: white;
}

#app-scroll {
    height: 1fr;
    scrollbar-size-vertical: 1;
    scrollbar-background: black;
    scrollbar-color: #585858;
    scrollbar-color-hover: #777777;
    scrollbar-color-active: #cfcfcf;
}

#root {
    layout: vertical;
    height: auto;
    padding: 0 0 0 1;
}

#transcript {
    height: auto;
    margin-top: 1;
    color: white;
}

#reader-label {
    height: 1;
    color: #8a8a8a;
    text-style: dim;
}

#reader-text {
    height: 3;
    color: #666666;
}

#recent-log {
    height: 28;
}

#working-line {
    height: 1;
    margin-top: 1;
}

#composer {
    height: 3;
    margin-top: 1;
    border-top: solid #444444;
    border-bottom: solid #444444;
}

#footer {
    height: 2;
    margin-top: 1;
}
"""


class BookReader(Static):
    """Intercepts mouse scroll at the widget level so VerticalScroll never sees it."""

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        app = self.app
        if isinstance(app, CodeNovelApp):
            app.book_offset -= SCROLL_STEP
            app._render_book_view()
        event.stop()
        event.prevent_default()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        app = self.app
        if isinstance(app, CodeNovelApp):
            app.book_offset += SCROLL_STEP
            app._render_book_view()
        event.stop()
        event.prevent_default()


class InsetScrollBarRender(ScrollBarRender):
    """Render a slim vertical scrollbar that reaches the full track."""

    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color = Color.parse("#555555"),
        bar_color: Color = Color.parse("bright_magenta"),
    ) -> Segments:
        if not vertical:
            return super().render_bar(
                size=size,
                virtual_size=virtual_size,
                window_size=window_size,
                position=position,
                thickness=thickness,
                vertical=vertical,
                back_color=back_color,
                bar_color=bar_color,
            )

        inner_size = size
        blank = " " * thickness
        thumb_glyph = "\u2590" * thickness

        upper_meta = {"@mouse.up": "scroll_up"}
        lower_meta = {"@mouse.up": "scroll_down"}
        thumb_meta = {"@mouse.down": "grab"}

        segments = [
            Segment(blank, Style(bgcolor=back_color, meta=upper_meta))
            for _ in range(inner_size)
        ]

        if window_size and inner_size and virtual_size and inner_size != virtual_size:
            bar_ratio = virtual_size / inner_size
            thumb_size = max(1, ceil(window_size / bar_ratio))

            if virtual_size - window_size <= 0:
                start_index = 0
            else:
                position_ratio = position / (virtual_size - window_size)
                start_index = round((inner_size - thumb_size) * position_ratio)

            start_index = max(0, min(start_index, inner_size - thumb_size))
            end_index = start_index + thumb_size

            thumb_style = Style(
                color=bar_color,
                bgcolor=back_color,
                meta=thumb_meta,
            )
            lower_style = Style(bgcolor=back_color, meta=lower_meta)

            segments = (
                [Segment(blank, Style(bgcolor=back_color, meta=upper_meta)) for _ in range(start_index)]
                + [Segment(thumb_glyph, thumb_style) for _ in range(thumb_size)]
                + [Segment(blank, lower_style) for _ in range(inner_size - end_index)]
            )

        return Segments(segments, new_lines=True)


class CodeNovelApp(App[None]):
    CSS = BASE_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_pause", "Pause"),
        Binding("j,down", "scroll_down", "Down"),
        Binding("k,up", "scroll_up", "Up"),
        Binding("pagedown", "page_down", "Page Down"),
        Binding("pageup", "page_up", "Page Up"),
    ]

    paused = reactive(False)

    def __init__(
        self,
        book_path: Path | None,
        task_title: str,
        model_name: str = "GPT 5.4",
        model_provider: str = "hi",
        model_full: str = "gpt-5.4 high",
        project_name: str | None = None,
        project_path: str | None = None,
        log_path: Path | None = None,
        bottom_interval: float = 6.0,
        follow_log_scroll: bool = False,
    ) -> None:
        super().__init__()
        self.book_path = book_path
        self.task_title = task_title
        self.bottom_interval = max(0.1, bottom_interval)
        self.follow_log_scroll = follow_log_scroll
        self.started_at = monotonic()
        self._book_source_lines: list[str] = []
        self._book_source_index = 0
        self._book_wrap_width = 80
        self._book_processing_complete = False
        self._highlight_gap_remaining = 0
        self._highlight_streak_active = False
        self.book_lines: list[str] = []
        self.book_offset = 0
        self._book_line_highlights: list[bool] = []
        self.recent_lines: list[Text] = []

        if log_path and log_path.exists():
            from codenovel.logparser import load_and_parse
            lines, groups = load_and_parse(log_path)
            self.engine: FakeLogEngine | ReplayEngine = ReplayEngine(lines, groups)
        else:
            self.engine = FakeLogEngine(task_title=task_title, seed=randint(1, 999_999))

        self.model_name = model_name
        self.model_provider = model_provider
        self.model_full = model_full
        self.project_name = project_name or "codex_moyu"
        self.project_path = project_path or str(Path.cwd())
        self.token_count = 12_400 + randint(0, 8_000)
        self.context_pct = randint(75, 90)

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Container(
                Static(id="transcript"),
                BookReader(id="reader-label"),
                BookReader(id="reader-text"),
                Static(id="recent-log"),
                Static(id="working-line"),
                Static(id="composer"),
                Static(id="footer"),
                id="root",
            ),
            id="app-scroll",
        )

    def on_mount(self) -> None:
        self._render_transcript()
        self._load_book()
        self._render_reader_label()
        self._render_composer()
        self._hide_scrollbars()
        self._render_footer()
        self._seed_logs()
        self._update_working_line()
        self.set_interval(self.bottom_interval, self._tick_bottom)
        self.set_interval(1.0, self._tick_clock)
        self.set_interval(0.08, self._tick_book_loader)

    def _render_transcript(self) -> None:
        preview = Text()
        for index, line in enumerate(self.engine.transcript_preview()):
            if index:
                preview.append("\n")
            preview.append_text(self._render_line(line))
        self.query_one("#transcript", Static).update(preview)

    def _load_book(self) -> None:
        book = load_book_text(self.book_path)
        self._book_source_lines = split_book_lines(book)
        width = self.size.width - 2
        self._book_wrap_width = width if width >= 20 else 80
        self._book_source_index = 0
        self._book_processing_complete = False
        self._highlight_gap_remaining = 0
        self._highlight_streak_active = False
        self.book_lines = []
        self.book_offset = 0
        self._book_line_highlights = []
        self._process_book_batch(INITIAL_BOOK_BATCH)
        self._render_book_view()

    def _render_book_view(self) -> None:
        self._ensure_book_capacity(self.book_offset + VISIBLE_BOOK_LINES + BOOK_LOOKAHEAD_LINES)
        total_lines = len(self.book_lines)
        max_offset = max(total_lines - VISIBLE_BOOK_LINES, 0)
        self.book_offset = max(0, min(self.book_offset, max_offset))
        visible = self.book_lines[self.book_offset : self.book_offset + VISIBLE_BOOK_LINES]
        while len(visible) < VISIBLE_BOOK_LINES:
            visible.append("")
        backgrounds = self._reader_overlay_backgrounds(VISIBLE_BOOK_LINES)
        block = Text(no_wrap=True)
        for i, (line, background) in enumerate(zip(visible, backgrounds, strict=False)):
            if i:
                block.append("\n")
            line_index = self.book_offset + i
            line_color = (
                READER_HIGHLIGHT_TEXT_COLOR
                if self._line_is_highlighted(line_index) and line.strip()
                else READER_TEXT_COLOR
            )
            line_style = Style(color=line_color, bgcolor=background)
            row = Text(no_wrap=True, style=line_style)
            row.append(line, style=line_style)
            block.append_text(self._pad_line(row, line_style))
        self.query_one("#reader-text", BookReader).update(block)

    def _render_reader_label(self) -> None:
        label_background = self._reader_overlay_backgrounds(VISIBLE_BOOK_LINES + 1)[0]
        self.query_one("#reader-label", BookReader).update(
            Text(
                "  inactive terminal output",
                style=Style(color=READER_LABEL_COLOR, bgcolor=label_background, dim=True),
            )
        )

    def _render_composer(self) -> None:
        composer = Text()
        composer.append("\u203a ", style="bold white")
        composer.append("Ask Codex to do anything", style="#666666")
        self.query_one("#composer", Static).update(composer)

    def _hide_scrollbars(self) -> None:
        app_scroll = self.query_one("#app-scroll", VerticalScroll)
        app_scroll.show_vertical_scrollbar = True
        app_scroll.vertical_scrollbar.renderer = InsetScrollBarRender

    def _format_token_count(self) -> str:
        if self.token_count >= 1_000_000:
            return f"{self.token_count / 1_000_000:.1f}M"
        if self.token_count >= 1_000:
            return f"{self.token_count / 1_000:.1f}k"
        return str(self.token_count)

    def _render_footer(self) -> None:
        ctx_usage = 100 - self.context_pct
        token_str = self._format_token_count()

        model_color = "#61D6D6"
        project_color = "#16C60C"
        token_color = "#B4009E"
        sep_color = "#888888"

        line1 = Text(no_wrap=True)
        line1.append("  ")
        line1.append("\u25c6 ", style=model_color)
        line1.append(f"{self.model_name} \u00b7{self.model_provider}", style=model_color)
        line1.append(" \u2502 ", style=sep_color)
        line1.append("\u25c6 ", style=project_color)
        line1.append(self.project_name, style=project_color)
        line1.append(" \u2502 ", style=sep_color)
        line1.append("\u25c6 ", style=token_color)
        line1.append(f"{ctx_usage}%", style=token_color)
        line1.append(" \u00b7 ", style=token_color)
        line1.append(f"{token_str} tokens", style=token_color)

        line2 = Text(no_wrap=True)
        line2.append("  ")
        line2.append(
            f"{self.model_full} \u00b7 {self.context_pct}% left \u00b7 {self.project_path}",
            style=sep_color,
        )

        block = Text(no_wrap=True)
        block.append_text(line1)
        block.append("\n")
        block.append_text(line2)
        self.query_one("#footer", Static).update(block)

    def _seed_logs(self) -> None:
        self.recent_lines = [self._render_user_prompt(self.engine.initial_prompt())]
        for _ in range(2):
            self._append_recent_group(self.engine.next_bottom_group())
        self._render_recent_log()

    def _tick_bottom(self) -> None:
        if self.paused:
            return
        if self.follow_log_scroll:
            self.book_offset += SCROLL_STEP
        self._append_recent_group(self.engine.next_bottom_group())
        self._render_recent_log()
        self._update_working_line()

    def _tick_clock(self) -> None:
        if not self.paused:
            self.token_count += randint(80, 350)
            if self.context_pct > 15:
                self.context_pct -= randint(0, 1)
        self._update_working_line()
        self._render_footer()

    def _update_working_line(self) -> None:
        elapsed = int(monotonic() - self.started_at)
        line = Text()
        line.append("\u2022 ", style="dim")
        if self.paused:
            line.append("Paused")
            line.append(f" ({elapsed}s \u2022 q to quit)", style="dim")
        else:
            phase_map = {
                "commentary": "Thinking through the next change",
                "explore": "Exploring the codebase",
                "inspect": "Investigating rendering code",
                "edit": "Editing the current approach",
                "test": "Running validation checks",
                "summarize": "Summarizing recent progress",
            }
            header = phase_map.get(self.engine.top_phase, "Working")
            line.append(header)
            line.append(f" ({elapsed}s \u2022 esc to interrupt)", style="dim")
        self.query_one("#working-line", Static).update(line)

    def _append_recent_group(self, lines: list[RenderedLine]) -> None:
        for line in lines:
            self.recent_lines.append(self._render_line(line))
        self.recent_lines = self.recent_lines[-28:]

    def _render_recent_log(self) -> None:
        block = Text()
        for index, line in enumerate(self.recent_lines):
            if index:
                block.append("\n")
            block.append_text(line)
        self.query_one("#recent-log", Static).update(block)
        self._render_reader_label()
        self._render_book_view()

    def _render_user_prompt(self, prompt: str) -> Text:
        line = Text()
        line.append("\u203a ", style="bold dim")
        line.append(prompt)
        return line

    def _tick_book_loader(self) -> None:
        if self._book_processing_complete:
            return
        previous_count = len(self.book_lines)
        self._process_book_batch(BACKGROUND_BOOK_BATCH)
        if len(self.book_lines) != previous_count:
            self._render_book_view()

    def _ensure_book_capacity(self, target_line_count: int) -> None:
        if target_line_count <= len(self.book_lines) or self._book_processing_complete:
            return
        pending_source_lines = target_line_count - len(self.book_lines)
        estimated_batch = max(INITIAL_BOOK_BATCH, pending_source_lines // max(VISIBLE_BOOK_LINES, 1))
        self._process_book_batch(estimated_batch)

    def _process_book_batch(self, source_line_count: int) -> None:
        if self._book_processing_complete:
            return
        end_index = min(self._book_source_index + source_line_count, len(self._book_source_lines))
        for line in self._book_source_lines[self._book_source_index : end_index]:
            wrapped_lines = wrap_line(line, self._book_wrap_width)
            for wrapped_line in wrapped_lines:
                self.book_lines.append(wrapped_line)
                self._book_line_highlights.append(self._next_book_line_highlight(wrapped_line))
        self._book_source_index = end_index
        self._book_processing_complete = self._book_source_index >= len(self._book_source_lines)

    def _line_is_highlighted(self, line_index: int) -> bool:
        return 0 <= line_index < len(self._book_line_highlights) and self._book_line_highlights[line_index]

    def _next_book_line_highlight(self, line: str) -> bool:
        if not line.strip():
            self._highlight_streak_active = False
            self._highlight_gap_remaining = max(self._highlight_gap_remaining, READER_MIN_GRAY_GAP)
            return False

        if self._highlight_streak_active:
            if random() < READER_HIGHLIGHT_STREAK_PROBABILITY:
                return True
            self._highlight_streak_active = False
            self._highlight_gap_remaining = max(READER_MIN_GRAY_GAP - 1, 0)
            return False

        if self._highlight_gap_remaining > 0:
            self._highlight_gap_remaining -= 1
            return False

        if random() < READER_HIGHLIGHT_PROBABILITY:
            self._highlight_streak_active = True
            return True

        return False

    def _reader_overlay_backgrounds(self, row_count: int) -> list[str | None]:
        backgrounds = [
            self._extract_background_color(self.recent_lines[index]) if index < len(self.recent_lines) else None
            for index in range(row_count)
        ]
        backgrounds.reverse()
        return backgrounds

    def _extract_background_color(self, text: Text) -> str | None:
        background = self._style_background_hex(text.style)
        if background:
            return background
        for span in text.spans:
            background = self._style_background_hex(span.style)
            if background:
                return background
        return None

    def _style_background_hex(self, style: Style | str | None) -> str | None:
        if style is None:
            return None
        resolved = style if isinstance(style, Style) else Style.parse(style)
        if resolved.bgcolor is None or resolved.bgcolor.triplet is None:
            return None
        return resolved.bgcolor.triplet.hex

    def _line_fill_width(self) -> int:
        width = self.size.width or 96
        return max(40, width - 4)

    def _pad_line(self, text: Text, fill_style: Style) -> Text:
        pad = self._line_fill_width() - cell_len(text.plain)
        if pad > 0:
            text.append(" " * pad, style=fill_style)
        return text

    def _stylize_diff_stats(self, text: Text, source: str, start: int, background: str) -> None:
        for match in _DIFF_STATS_RE.finditer(source):
            plus_start, plus_end = match.start(1), match.end(1)
            minus_start, minus_end = match.start(2), match.end(2)
            text.stylize(
                Style(color="#73C991", bgcolor=background, bold=True),
                start + plus_start - 1,
                start + plus_end,
            )
            text.stylize(
                Style(color="#F14C4C", bgcolor=background, bold=True),
                start + minus_start - 1,
                start + minus_end,
            )

    def _stylize_matches(
        self,
        text: Text,
        source: str,
        pattern: re.Pattern[str],
        style: Style,
        start: int,
    ) -> None:
        for match in pattern.finditer(source):
            text.stylize(style, start + match.start(), start + match.end())

    def _apply_code_highlighting(
        self,
        text: Text,
        code: str,
        start: int,
        background: str,
    ) -> None:
        self._stylize_matches(
            text,
            code,
            _CODE_KEYWORD_RE,
            Style(color="#569CD6", bgcolor=background, bold=True),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_TYPE_RE,
            Style(color="#4EC9B0", bgcolor=background),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_FUNCTION_RE,
            Style(color="#DCDCAA", bgcolor=background),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_MACRO_RE,
            Style(color="#C586C0", bgcolor=background),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_NUMBER_RE,
            Style(color="#B5CEA8", bgcolor=background),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_STRING_RE,
            Style(color="#CE9178", bgcolor=background),
            start,
        )
        self._stylize_matches(
            text,
            code,
            _CODE_COMMENT_RE,
            Style(color="#6A9955", bgcolor=background, italic=True),
            start,
        )

    def _render_diff_line(self, raw: str, kind: str) -> Text:
        palette = {
            "diff_add": {
                "background": "#213a2b",
                "foreground": "#D6EFD8",
                "gutter": "#587C5C",
                "marker": "#81B88B",
            },
            "diff_del": {
                "background": "#4a221d",
                "foreground": "#F0D7DC",
                "gutter": "#9E6A75",
                "marker": "#C74E39",
            },
            "diff_ctx": {
                "background": "#000000",
                "foreground": "#C9D1D9",
                "gutter": "#6E7681",
                "marker": "#6E7681",
            },
        }[kind]

        match = _DIFF_LINE_RE.match(raw)
        if match:
            line_number, marker, code = match.groups()
        else:
            line_number, marker, code = None, " ", raw

        background = palette["background"]
        base_style = Style(color=palette["foreground"], bgcolor=background)
        gutter_style = Style(color=palette["gutter"], bgcolor=background, dim=True)
        marker_style = Style(color=palette["marker"], bgcolor=background, bold=True)

        text = Text(style=base_style, no_wrap=True)
        text.append("    ", style=base_style)
        if line_number:
            text.append(f"{line_number:>4} ", style=gutter_style)
        else:
            text.append("     ", style=gutter_style)
        text.append(marker if marker in "+-" else " ", style=marker_style if marker in "+-" else gutter_style)
        text.append(" ", style=base_style)
        code_start = len(text)
        text.append(code, style=base_style)
        self._apply_code_highlighting(text, code, code_start, background)
        return self._pad_line(text, base_style)

    def _render_diff_blank_line(self, raw: str) -> Text:
        background = "#000000"
        base_style = Style(color="#C9D1D9", bgcolor=background)
        gutter_style = Style(color="#6E7681", bgcolor=background, dim=True)
        text = Text(style=base_style, no_wrap=True)
        text.append("    ", style=base_style)
        text.append(f"{raw:>4} ", style=gutter_style)
        text.append("  ", style=base_style)
        return self._pad_line(text, base_style)

    def _render_fold_marker_line(self, raw: str) -> Text:
        background = "#000000"
        base_style = Style(color="#7D8590", bgcolor=background, dim=True)
        marker_style = Style(color="#8B949E", bgcolor=background)
        text = Text(style=base_style, no_wrap=True)
        text.append("    ", style=base_style)
        text.append("     ", style=base_style)
        text.append(raw, style=marker_style)
        return self._pad_line(text, base_style)

    def _render_edit_summary(self, raw: str) -> Text:
        background = "#000000"
        base_style = Style(color="#D8DEE9", bgcolor=background)
        bullet_style = Style(color="#7D8590", bgcolor=background, dim=True)
        text = Text(style=base_style, no_wrap=True)
        text.append("\u2022 ", style=bullet_style)
        start = len(text)
        text.append(raw, style=Style(color="#D8DEE9", bgcolor=background, bold=True))
        self._stylize_diff_stats(text, raw, start, background)
        return self._pad_line(text, base_style)

    def _render_path_summary(self, raw: str) -> Text:
        background = "#000000"
        base_style = Style(color="#C9D1D9", bgcolor=background)
        prefix_style = Style(color="#6E7681", bgcolor=background, dim=True)
        path_style = Style(color="#58A6FF", bgcolor=background, bold=True)
        text = Text(style=base_style, no_wrap=True)
        text.append("  \u2514 ", style=prefix_style)
        match = _PATH_SUMMARY_RE.match(raw)
        if match:
            path, stats = match.groups()
            text.append(path, style=path_style)
            stats_start = len(text)
            text.append(stats, style=base_style)
            self._stylize_diff_stats(text, stats, stats_start, background)
        else:
            text.append(raw, style=path_style)
        return self._pad_line(text, base_style)

    def _render_child_deep(self, raw: str) -> Text:
        stripped = raw.strip()
        normalized = stripped.lstrip("? ").lstrip("└│├─ ")
        if _DIFF_BLANK_RE.match(stripped):
            return self._render_diff_blank_line(stripped)
        if stripped in {"...", "..", "... "}:
            return self._render_fold_marker_line(stripped)
        if _PATH_SUMMARY_RE.match(raw):
            return self._render_path_summary(raw)
        if _PATH_SUMMARY_RE.match(normalized):
            return self._render_path_summary(normalized)

        text = Text()
        text.append("    ")
        text.append(raw, style="dim")
        return text

    def _render_plain(self, raw: str) -> Text:
        normalized = raw.lstrip("? ").lstrip(".>").strip()
        if normalized.startswith("Edited ") and _DIFF_STATS_RE.search(normalized):
            return self._render_edit_summary(normalized)
        text = Text()
        text.append(raw)
        return text

    def _render_line(self, line: RenderedLine) -> Text:
        text = Text()
        k = line.kind

        diff_match = _DIFF_LINE_RE.match(line.text)
        if k in {"plain", "child_deep", "command_output"} and diff_match:
            _, marker, _ = diff_match.groups()
            inferred_kind = {"+" : "diff_add", "-" : "diff_del", " " : "diff_ctx"}[marker]
            return self._render_diff_line(line.text, inferred_kind)

        if k == "user_prompt":
            text.append("\u203a ", style="bold white")
            text.append(line.text, style="bold white")
        elif k == "thinking":
            text.append("\u2022 ", style="#666666")
            text.append(line.text, style="#999999 italic")
        elif k in {"commentary", "event"}:
            text.append("\u2022 ", style="dim")
            text.append(line.text)
        elif k == "command_run":
            text.append("\u2022 Ran ", style="dim")
            text.append(line.text, style="cyan")
        elif k == "command_output":
            text.append("  \u2514 ", style="dim")
            text.append(line.text)
        elif k == "child":
            text.append("  \u2514 ", style="dim")
            text.append(line.text, style="cyan")
        elif k == "child_deep":
            text = self._render_child_deep(line.text)
        elif k == "command":
            text.append("  ")
            if line.text.startswith("$ "):
                text.append("$ ", style="magenta")
                text.append(line.text[2:])
            else:
                text.append(line.text, style="cyan")
        elif k == "success":
            text.append("    ")
            text.append("\u2713 ", style="green bold")
            text.append(line.text, style="dim")
        elif k == "queue":
            text.append("  \u2192 ", style="dim")
            text.append(line.text)
        elif k == "summary":
            text.append("\u2022 ", style="dim")
            text.append(line.text, style="dim")
        elif k == "file_path":
            text.append("    ")
            text.append(line.text, style="bold blue")
        elif k == "diff_add":
            text = self._render_diff_line(line.text, "diff_add")
        elif k == "diff_del":
            text = self._render_diff_line(line.text, "diff_del")
        elif k == "diff_ctx":
            text = self._render_diff_line(line.text, "diff_ctx")
        elif k == "warning":
            text.append(f"  \u26a0 {line.text}", style="yellow")
        elif k == "progress":
            text.append(f"  \u25b6 {line.text}", style="bright_blue")
        elif k == "separator":
            text.append("\u2500" * 100, style="dim")
        elif k == "waited":
            text.append("\u2022 ", style="#666666")
            text.append(line.text, style="#666666")
        elif k == "edited":
            text = self._render_edit_summary(line.text)
        elif k == "interrupted":
            text.append("\u25a0 ", style="red bold")
            text.append(line.text, style="red")
        elif k == "header_box":
            text.append(line.text, style="#61D6D6 dim")
        elif k == "work_timer":
            text.append(f"\u2500 {line.text} ", style="dim")
        elif k == "tip":
            text.append(f"  {line.text}", style="dim")
        else:
            text = self._render_plain(line.text)
        return text

    # --- actions ---

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        self._update_working_line()

    def action_scroll_down(self) -> None:
        self.book_offset += SCROLL_STEP
        self._render_book_view()

    def action_scroll_up(self) -> None:
        self.book_offset -= SCROLL_STEP
        self._render_book_view()

    def action_page_down(self) -> None:
        self.book_offset += VISIBLE_BOOK_LINES
        self._render_book_view()

    def action_page_up(self) -> None:
        self.book_offset -= VISIBLE_BOOK_LINES
        self._render_book_view()

