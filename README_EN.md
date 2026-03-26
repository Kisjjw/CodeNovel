# CodeNovel

CodeNovel is a Textual-based terminal toy that recreates the look of a Codex-style coding session while hiding a TXT novel in the middle of the screen as dim "inactive output".

It can run in two modes:
- Synthetic mode: generates a believable stream of fake coding activity, diffs, warnings, and status updates.
- Replay mode: parses a real Codex CLI transcript and replays it inside the same interface.

The result is half terminal simulator, half stealth text reader.

## Demo

[![CodeNovel demo animation](./demo.gif)](./demo.mp4)

- Animated preview: [`demo.gif`](./demo.gif)
- Image preview: [`demo.jpg`](./demo.jpg)
- Video demo: [`demo.mp4`](./demo.mp4)

## Why This Exists

CodeNovel is built for a very specific joke and aesthetic:
- the screen looks like an AI coding session in progress
- the center pane quietly contains the text you actually want to read
- the surrounding transcript keeps the terminal feeling alive

If you like terminal UI experiments, Codex-style visuals, or weird reading tools, this project is for you.

## Features

- Codex-like terminal layout built with [Textual](https://github.com/Textualize/textual) and Rich
- Hidden TXT reader rendered as dim, inactive terminal output
- Synthetic transcript generator with commands, summaries, diffs, warnings, and progress lines
- Real log replay mode via `--log`
- Keyboard and mouse-wheel reading controls for the hidden text pane
- CLI toggle for the hidden reader's occasional pure-white highlight lines
- Automatic per-book reading position memory using original TXT line numbers
- CLI option to start from a specific line in the original TXT file
- Footer metadata for model, provider, token count, and project path
- UTF-8 and `gb18030` TXT decoding support

## Requirements

- Python 3.10+
- A terminal with decent Unicode and 24-bit color support

For the cleanest visual result, use Windows Terminal, iTerm2, WezTerm, or another modern terminal emulator. It will still run in classic `cmd`, but glyphs and colors may look rougher.

## Installation

Install from the project root:

```bash
pip install .
```

For development:

```bash
pip install -e .
```

If your environment does not expose the `codenovel` script on `PATH`, use:

```bash
python -m codenovel
```

On Windows, this repo also includes a local [`codenovel.bat`](./codenovel.bat) wrapper for convenience when you launch from the project directory.

## Quick Start

Recommended test command:

```bash
.\codenovel .\demo_novel.txt --log .\codex_log.txt --bottom-interval 1.5
```

Run with a TXT file:

```bash
codenovel path/to/novel.txt
```

Set a custom fake task title:

```bash
codenovel path/to/novel.txt --title "Refactor transcript renderer"
```

Replay a real Codex terminal log instead of generating fake activity:

```bash
codenovel path/to/novel.txt --log path/to/codex-session.txt
```

Speed up the lower activity stream:

```bash
codenovel path/to/novel.txt --bottom-interval 2.5
```

Make the novel pane auto-scroll together with the lower log stream:

```bash
codenovel path/to/novel.txt --follow-log-scroll
```

Disable the hidden reader's occasional pure-white highlight lines:

```bash
codenovel path/to/novel.txt --no-reader-highlight
```

Start from line 1200 in the original TXT file. This overrides saved reading progress:

```bash
codenovel path/to/novel.txt --start-line 1200
```

Run without a TXT file to show the built-in placeholder instructions:

```bash
codenovel
```

## Controls

- `j` or `Down`: scroll the hidden TXT reader down
- `k` or `Up`: scroll the hidden TXT reader up
- `PageDown`: scroll down faster
- `PageUp`: scroll up faster
- `space`: pause or resume the synthetic / replayed activity
- `q`: quit
- Mouse wheel over the center reader: scroll the TXT content without moving the main transcript

## Command-Line Options

```text
usage: codenovel [-h] [--title TITLE] [--model MODEL] [--provider PROVIDER]
                 [--model-full MODEL_FULL] [--project PROJECT] [--log LOG]
                 [--bottom-interval BOTTOM_INTERVAL] [--follow-log-scroll]
                 [--no-follow-log-scroll] [--reader-highlight]
                 [--no-reader-highlight] [--start-line START_LINE]
                 [book]
```

Arguments:

- `book`: path to a `.txt` file
- `--title`: fake task title shown in the transcript
- `--model`: short model label shown in the footer
- `--provider`: provider tag shown next to the model name
- `--model-full`: full model description for the footer second line
- `--project`: project name shown in the footer
- `--log`: path to a real Codex terminal log to parse and replay
- `--bottom-interval`: seconds between bottom stream updates
- `--follow-log-scroll`: auto-scroll the TXT pane with lower log updates
- `--no-follow-log-scroll`: keep TXT scrolling independent
- `--reader-highlight`: enable occasional pure-white highlight lines in the hidden TXT reader
- `--no-reader-highlight`: disable the hidden TXT reader's random pure-white highlight lines
- `--start-line`: start reading from this 1-based line number in the original TXT file, overriding saved progress

## Input Notes

- Only `.txt` books are supported right now.
- TXT files are first read as UTF-8, then retried as `gb18030` if UTF-8 decoding fails.
- If the path does not exist, the app shows an inline error message inside the reader pane.
- Empty TXT files fall back to built-in placeholder content.
- Reading progress is stored by original TXT line number in `~/.codenovel/progress.json`.
- If `--start-line` is not provided, the app restores the last saved reading position by default.

## How It Works

CodeNovel is organized around a few small components:

- [`codenovel/ui_app.py`](./codenovel/ui_app.py): the main Textual UI, layout, colors, scrolling behavior, and diff rendering
- [`codenovel/simulator.py`](./codenovel/simulator.py): synthetic transcript generation
- [`codenovel/logparser.py`](./codenovel/logparser.py): parser for replaying real Codex CLI logs
- [`codenovel/progress.py`](./codenovel/progress.py): per-book reading progress persistence
- [`codenovel/reader.py`](./codenovel/reader.py): TXT loading and line splitting
- [`codenovel/cli.py`](./codenovel/cli.py): argument parsing and app startup

## Development

Run the app directly from source:

```bash
python -m codenovel demo_novel.txt
```

Install editable dependencies:

```bash
pip install -e .
```


Useful files in this repo:

- [`demo_novel.txt`](./demo_novel.txt): sample TXT content
- [`pyproject.toml`](./pyproject.toml): package metadata and dependencies

## License

This project is published under the MIT license according to [`pyproject.toml`](./pyproject.toml).
