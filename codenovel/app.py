from __future__ import annotations

from pathlib import Path
from random import randint
from time import monotonic

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.widgets import RichLog, Static

from codenovel.reader import load_book_text, split_book_lines
from codenovel.simulator import FakeLogEngine, RenderedLine, ReplayEngine


BASE_CSS = """
Screen {
    background: black;
    color: white;
}

#root {
    layout: vertical;
    height: auto;
    padding: 0 1;
}

#app-scroll {
    height: 1fr;
    scrollbar-size-vertical: 0;
    scrollbar-background: transparent;
    scrollbar-color: transparent;
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

#reader-scroll {
    height: 4;
    margin-top: 1;
}

#reader-text {
    color: #adadad;
    text-style: dim;
}

#recent-log {
    height: 6;
    margin-top: 1;
    scrollbar-size-vertical: 0;
    scrollbar-color: transparent;
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
    ) -> None:
        super().__init__()
        self.book_path = book_path
        self.task_title = task_title
        self.started_at = monotonic()
        self.book_lines: list[str] = []
        self.book_offset = 0

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
                Static(id="reader-label"),
                Static(id="reader-text"),
                RichLog(id="recent-log", wrap=True, highlight=False, markup=False),
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
        self.set_interval(1.35, self._tick_bottom)
        self.set_interval(1.0, self._tick_clock)

    def _render_transcript(self) -> None:
        preview = Text()
        for index, line in enumerate(self.engine.transcript_preview()):
            if index:
                preview.append("\n")
            preview.append_text(self._render_line(line))
        self.query_one("#transcript", Static).update(preview)

    def _load_book(self) -> None:
        book = load_book_text(self.book_path)
        self.book_lines = split_book_lines(book)
        self.book_offset = 0
        self._render_book_view()

    def _render_book_view(self) -> None:
        total_lines = len(self.book_lines)
        max_offset = max(total_lines - 4, 0)
        self.book_offset = max(0, min(self.book_offset, max_offset))
        visible = self.book_lines[self.book_offset : self.book_offset + 4]
        while len(visible) < 4:
            visible.append("  ")
        self.query_one("#reader-text", Static).update("\n".join(visible))

    def _render_reader_label(self) -> None:
        self.query_one("#reader-label", Static).update(
            Text("  inactive terminal output", style="dim")
        )

    def _render_composer(self) -> None:
        composer = Text()
        composer.append("\u203a ", style="bold white")
        composer.append("Ask Codex to do anything", style="#666666")
        self.query_one("#composer", Static).update(composer)

    def _hide_scrollbars(self) -> None:
        self.query_one("#app-scroll", VerticalScroll).show_vertical_scrollbar = False
        self.query_one("#recent-log", RichLog).show_vertical_scrollbar = False

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
        recent = self.query_one("#recent-log", RichLog)
        recent.write(self._render_user_prompt(self.engine.initial_prompt()))
        for _ in range(2):
            self._write_group(recent, self.engine.next_bottom_group())

    def _tick_bottom(self) -> None:
        if self.paused:
            return
        self._write_group(self.query_one("#recent-log", RichLog), self.engine.next_bottom_group())
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
            header = self.engine.working_status(elapsed, self.paused)
            idx = header.find(" (")
            if idx > 0:
                line.append(header[:idx])
                line.append(header[idx:], style="dim")
            else:
                line.append(header)
        self.query_one("#working-line", Static).update(line)

    def _write_group(self, widget: RichLog, lines: list[RenderedLine]) -> None:
        for line in lines:
            widget.write(self._render_line(line))

    def _render_user_prompt(self, prompt: str) -> Text:
        line = Text()
        line.append("\u203a ", style="bold dim")
        line.append(prompt)
        return line

    def _render_line(self, line: RenderedLine) -> Text:
        text = Text()
        k = line.kind

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
            text.append("    ")
            text.append(line.text, style="dim")
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
            text.append(f"    {line.text}", style="green")
        elif k == "diff_del":
            text.append(f"    {line.text}", style="red")
        elif k == "diff_ctx":
            text.append(f"    {line.text}", style="dim")
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
            text.append("\u2022 ", style="dim")
            text.append(line.text, style="bold")
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
            text.append(line.text)
        return text

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        self._update_working_line()

    def action_scroll_down(self) -> None:
        self.book_offset += 1
        self._render_book_view()

    def action_scroll_up(self) -> None:
        self.book_offset -= 1
        self._render_book_view()

    def action_page_down(self) -> None:
        self.book_offset += 4
        self._render_book_view()

    def action_page_up(self) -> None:
        self.book_offset -= 4
        self._render_book_view()
