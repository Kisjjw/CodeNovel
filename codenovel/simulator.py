from __future__ import annotations

from dataclasses import dataclass, field
from itertools import cycle
from random import Random


TOP_PHASES = ("commentary", "explore", "inspect", "edit", "test", "summarize")
BOTTOM_PHASES = ("follow_up", "command", "summary", "diff", "progress", "warning")

CODE_SNIPPETS_ADD = [
    '    let status = RenderStatus::new(ctx.elapsed());',
    '    self.footer.set_visible(true);',
    '    buf.push_str(&format!("{} tokens", usage.total));',
    '    if let Some(ref msg) = self.pending_message {',
    '        composer.render_hint(frame, area);',
    '    }',
    '    let layout = Layout::vertical([Constraint::Min(1), Constraint::Length(3)]);',
    '    terminal.draw(|f| ui::draw(f, &mut app))?;',
    '    pub fn update_scroll_offset(&mut self, delta: i32) {',
    '        self.offset = self.offset.saturating_add_signed(delta as isize);',
    '    async fn handle_response(&mut self, resp: Response) -> Result<()> {',
    '        let chunks = resp.stream().chunks(4096);',
    '        self.history.push(Entry::assistant(content.clone()));',
    '    fn render_diff_line(&self, line: &DiffLine, area: Rect, buf: &mut Buffer) {',
    '        let style = match line.kind { Added => Style::new().green(), _ => Style::reset() };',
    '    let config = Config::from_env().unwrap_or_default();',
    '    tracing::info!("session started, model={}", self.model);',
    '    let client = Client::builder().timeout(Duration::from_secs(30)).build()?;',
    '        .map(|chunk| chunk.choices[0].delta.content.clone())',
    '        .collect::<Vec<_>>();',
    '    self.token_count += response.usage.total_tokens;',
    '    frame.render_widget(Paragraph::new(text).wrap(Wrap { trim: false }), inner);',
    '    let span = Span::styled(format!(" {} ", label), modifier);',
    '    crossterm::execute!(stdout(), EnterAlternateScreen, EnableMouseCapture)?;',
]

CODE_SNIPPETS_DEL = [
    '    let status = format!("running ({}s)", elapsed);',
    '    self.footer.set_visible(false);',
    '    // TODO: clean up token counting',
    '    buf.push_str("tokens: unknown");',
    '    if self.pending_message.is_some() {',
    '        composer.clear();',
    '    let layout = Layout::default().direction(Direction::Vertical);',
    '    terminal.draw(|f| f.render_widget(&app, f.size()))?;',
    '    pub fn scroll(&mut self, n: i32) {',
    '        self.offset += n as usize;',
    '    fn handle_response(&mut self, resp: String) {',
    '        let body = resp.clone();',
    '        self.history.push(content.clone());',
    '    fn render_line(&self, text: &str, buf: &mut Buffer) {',
    '        let style = Style::default();',
    '    let config = Config::default();',
    '    println!("session started");',
    '    let client = reqwest::Client::new();',
    '        .map(|c| c.to_string())',
    '        .collect::<String>();',
    '    self.token_count += 1;',
    '    frame.render_widget(Paragraph::new(text), inner);',
    '    let span = Span::raw(label);',
    '    crossterm::execute!(stdout(), EnterAlternateScreen)?;',
]

CODE_SNIPPETS_CONTEXT = [
    '    use std::io::{self, Write};',
    '    use ratatui::prelude::*;',
    '',
    '    impl App {',
    '        Ok(())',
    '    }',
    '    #[derive(Debug, Clone)]',
    '    pub struct SessionState {',
    '        model: String,',
    '        history: Vec<Entry>,',
    '    }',
    '    mod tests {',
    '        use super::*;',
    '        #[test]',
    '        fn test_render() {',
    '            let app = App::default();',
    '            assert!(app.is_ready());',
]


@dataclass(frozen=True)
class RenderedLine:
    kind: str
    text: str


@dataclass
class SessionContext:
    task_title: str
    seed: int
    src_count: int = 18
    test_count: int = 7
    doc_count: int = 4
    module_a: str = "tui/src/bottom_pane/footer.rs"
    module_b: str = "tui/src/chatwidget.rs"
    module_c: str = "tui/src/history_cell.rs"
    file_a: str = "tui/src/app.rs"
    file_b: str = "tui/src/bottom_pane/chat_composer.rs"
    symbol_name: str = "render_status_footer"
    test_name: str = "tests/test_session_render.py::test_dimmed_reader"
    latency: int = 34
    phase_cycle: cycle = field(init=False, repr=False)
    bottom_cycle: cycle = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.phase_cycle = cycle(TOP_PHASES)
        self.bottom_cycle = cycle(BOTTOM_PHASES)


class FakeLogEngine:
    def __init__(self, task_title: str, seed: int = 7) -> None:
        self.random = Random(seed)
        self.context = SessionContext(task_title=task_title, seed=seed)
        self.top_phase = next(self.context.phase_cycle)
        self.bottom_phase = next(self.context.bottom_cycle)
        self.top_counter = 0
        self.bottom_counter = 0

    def _render_template(self, template: str) -> str:
        self.context.src_count += self.random.choice((0, 1))
        self.context.test_count += self.random.choice((0, 0, 1))
        self.context.doc_count += self.random.choice((0, 0, 1))
        self.context.latency = max(12, self.context.latency + self.random.randint(-4, 7))
        return template.format(**self.context.__dict__)

    def _random_diff_hunk(self, n_del: int = 2, n_add: int = 3) -> list[RenderedLine]:
        lines: list[RenderedLine] = []
        ctx = self.random.choice(CODE_SNIPPETS_CONTEXT)
        if ctx:
            lines.append(RenderedLine("diff_ctx", f"  {ctx}"))
        for _ in range(n_del):
            lines.append(RenderedLine("diff_del", f"- {self.random.choice(CODE_SNIPPETS_DEL)}"))
        for _ in range(n_add):
            lines.append(RenderedLine("diff_add", f"+ {self.random.choice(CODE_SNIPPETS_ADD)}"))
        ctx2 = self.random.choice(CODE_SNIPPETS_CONTEXT)
        if ctx2:
            lines.append(RenderedLine("diff_ctx", f"  {ctx2}"))
        return lines

    def initial_prompt(self) -> str:
        return self.context.task_title

    def transcript_preview(self, groups: int = 26) -> list[RenderedLine]:
        lines: list[RenderedLine] = [
            RenderedLine(
                "commentary",
                "I'm going to inspect the transcript layout before making any visible changes.",
            )
        ]
        for _ in range(groups):
            lines.extend(self.next_top_group())
        return lines

    def working_status(self, elapsed_seconds: int, paused: bool) -> str:
        if paused:
            return f"Paused ({elapsed_seconds}s \u2022 q to quit)"
        phase_map = {
            "commentary": "Thinking through the next change",
            "explore": "Exploring the codebase",
            "inspect": "Investigating rendering code",
            "edit": "Editing the current approach",
            "test": "Running validation checks",
            "summarize": "Summarizing recent progress",
        }
        label = phase_map.get(self.top_phase, "Working")
        return f"{label} ({elapsed_seconds}s \u2022 esc to interrupt)"

    def next_top_group(self) -> list[RenderedLine]:
        if self.top_counter and self.top_counter % 4 == 0:
            self.top_phase = next(self.context.phase_cycle)
        self.top_counter += 1

        if self.top_phase == "commentary":
            template = self.random.choice(
                [
                    "I'm going to inspect the rendering path around {symbol_name} before changing anything.",
                    "I want to confirm where the current session UI is composing history cells and status rows.",
                    "I'm tracing how '{task_title}' should read in the terminal before touching the fake transcript.",
                ]
            )
            return [RenderedLine("commentary", self._render_template(template))]

        if self.top_phase == "explore":
            search = self.random.choice(
                [
                    "Search status footer layout",
                    "Search queued message rendering",
                    "Search transcript viewport",
                    "Search terminal title update",
                ]
            )
            read_target = self.random.choice(
                [
                    self.context.module_a,
                    self.context.module_b,
                    self.context.module_c,
                    self.context.file_a,
                ]
            )
            return [
                RenderedLine("event", "Explored"),
                RenderedLine("child", search),
                RenderedLine("child_deep", f"Read {read_target}"),
            ]

        if self.top_phase == "inspect":
            template = self.random.choice(
                [
                    "Inspecting how dim secondary text is rendered in long-running sessions.",
                    "Checking whether the working indicator and footer collapse conflict at narrow widths.",
                    "Reviewing how file reads and status hints are grouped together in the transcript.",
                ]
            )
            return [RenderedLine("event", self._render_template(template))]

        if self.top_phase == "edit":
            target = self.random.choice(
                [self.context.file_a, self.context.file_b, self.context.module_a]
            )
            lines: list[RenderedLine] = [
                RenderedLine("event", f"Edited {target}"),
                RenderedLine("file_path", target),
            ]
            n_del = self.random.randint(1, 3)
            n_add = self.random.randint(1, 4)
            lines.extend(self._random_diff_hunk(n_del, n_add))
            return lines

        if self.top_phase == "test":
            command = self.random.choice(
                [
                    "$ pytest tests/test_session_render.py -q",
                    "$ rg -n \"context left\" tui/src",
                    "$ python -m build",
                    "$ git diff --stat",
                    "$ cargo test -p codex-tui --lib",
                ]
            )
            result = self.random.choice(
                [
                    f"{self.random.randint(3, 12)} passed in {self.random.uniform(0.2, 1.8):.2f}s",
                    "render path confirmed",
                    f"p95={self.context.latency}ms",
                    "no unexpected regressions",
                    f"test result: ok. {self.random.randint(5, 20)} passed; 0 failed",
                ]
            )
            warn = self.random.choice(
                [
                    None,
                    None,
                    f"warning: unused variable `tmp` in {self.context.module_b}",
                    f"warning: {self.context.module_c}:42 \u2014 consider simplifying this match arm",
                ]
            )
            lines = [
                RenderedLine("event", "Ran validation"),
                RenderedLine("command", command),
                RenderedLine("success", result),
            ]
            if warn:
                lines.append(RenderedLine("warning", warn))
            return lines

        template = self.random.choice(
            [
                "Summarizing the current pass before the next synthetic turn.",
                "The layout is converging on a more transcript-first terminal shape.",
                "Recent edits are keeping the output calm while the center block stays dim.",
            ]
        )
        return [RenderedLine("summary", self._render_template(template))]

    def next_bottom_group(self) -> list[RenderedLine]:
        if self.bottom_counter and self.bottom_counter % 3 == 0:
            self.bottom_phase = next(self.context.bottom_cycle)
        self.bottom_counter += 1

        if self.bottom_phase == "follow_up":
            return [
                RenderedLine("event", "Queued follow-up messages"),
                RenderedLine("queue", self.context.task_title),
            ]

        if self.bottom_phase == "command":
            command = self.random.choice(
                [
                    f"$ rg -n \"{self.context.symbol_name}\" {self.context.file_a}",
                    f"$ sed -n '1,140p' {self.context.file_b}",
                    f"$ pytest {self.context.test_name} -q",
                    "$ git status --short",
                    f"$ cat {self.context.module_a}",
                ]
            )
            return [
                RenderedLine("command", command),
                RenderedLine("child_deep", "capturing output for transcript"),
            ]

        if self.bottom_phase == "diff":
            target = self.random.choice(
                [self.context.file_a, self.context.file_b, self.context.module_a]
            )
            lines: list[RenderedLine] = [
                RenderedLine("event", f"Applied patch to {target}"),
                RenderedLine("file_path", target),
            ]
            n_del = self.random.randint(1, 2)
            n_add = self.random.randint(1, 3)
            lines.extend(self._random_diff_hunk(n_del, n_add))
            return lines

        if self.bottom_phase == "progress":
            pct = self.random.randint(35, 99)
            step = self.random.choice(
                [
                    "Compiling workspace",
                    "Running test suite",
                    "Indexing source files",
                    "Building dependency graph",
                ]
            )
            return [
                RenderedLine("progress", f"[{pct}%] {step}"),
                RenderedLine("success", f"completed {self.random.randint(20, 200)} items"),
            ]

        if self.bottom_phase == "warning":
            warn = self.random.choice(
                [
                    f"unused import `HashMap` in {self.context.module_b}:3",
                    f"variable `buf` shadows outer binding in {self.context.module_c}:87",
                    f"deprecated API call at {self.context.file_a}:214",
                    f"possible performance issue in {self.context.file_b}:56",
                ]
            )
            return [
                RenderedLine("warning", warn),
                RenderedLine("child_deep", "non-blocking, continuing"),
            ]

        summary = self.random.choice(
            [
                "Recent checks look stable enough for another pass.",
                "The fake activity stream is staying coherent across the last few updates.",
                "Current output density is close to the real Codex CLI pacing.",
            ]
        )
        return [RenderedLine("summary", summary)]


class ReplayEngine:
    """Replay parsed real Codex log lines instead of generating fake content."""

    def __init__(
        self,
        all_lines: list[RenderedLine],
        groups: list[list[RenderedLine]],
        transcript_ratio: float = 0.75,
        max_transcript_lines: int = 600,
    ) -> None:
        split = max(1, int(len(groups) * transcript_ratio))
        self._transcript_groups = groups[:split]
        self._stream_groups = groups[split:] or groups[-10:]
        self._stream_idx = 0

        self._first_prompt = "Summarize recent commits"
        for line in all_lines:
            if line.kind == "user_prompt":
                self._first_prompt = line.text
                break

        transcript_lines: list[RenderedLine] = []
        for g in self._transcript_groups:
            transcript_lines.extend(g)
        if len(transcript_lines) > max_transcript_lines:
            transcript_lines = transcript_lines[-max_transcript_lines:]
        self._transcript_lines = transcript_lines

        self._phase_cycle = cycle(TOP_PHASES)
        self.top_phase = next(self._phase_cycle)
        self._tick = 0

    def initial_prompt(self) -> str:
        return self._first_prompt

    def transcript_preview(self, groups: int = 0) -> list[RenderedLine]:
        return self._transcript_lines

    def next_bottom_group(self) -> list[RenderedLine]:
        if not self._stream_groups:
            return [RenderedLine("thinking", "Analyzing codebase structure...")]
        group = self._stream_groups[self._stream_idx % len(self._stream_groups)]
        self._stream_idx += 1
        self._tick += 1
        if self._tick % 4 == 0:
            self.top_phase = next(self._phase_cycle)
        return group

    def working_status(self, elapsed_seconds: int, paused: bool) -> str:
        if paused:
            return f"Paused ({elapsed_seconds}s \u2022 q to quit)"
        phase_map = {
            "commentary": "Thinking through the next change",
            "explore": "Exploring the codebase",
            "inspect": "Investigating rendering code",
            "edit": "Editing the current approach",
            "test": "Running validation checks",
            "summarize": "Summarizing recent progress",
        }
        label = phase_map.get(self.top_phase, "Working")
        return f"{label} ({elapsed_seconds}s \u2022 esc to interrupt)"
