from __future__ import annotations

import argparse
from pathlib import Path

from codenovel.ui_app import CodeNovelApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codenovel",
        description="Codex-like fake AI coding terminal with a hidden TXT novel reader.",
    )
    parser.add_argument(
        "book",
        nargs="?",
        default=None,
        help="Path to a TXT novel file.",
    )
    parser.add_argument(
        "--title",
        default="Summarize recent commits",
        help="Fake task title shown in the transcript.",
    )
    parser.add_argument(
        "--model",
        default="GPT 5.4",
        help="Model name shown in footer (e.g. 'GPT 5.4').",
    )
    parser.add_argument(
        "--provider",
        default="hi",
        help="Model provider tag shown after model name (e.g. 'hi').",
    )
    parser.add_argument(
        "--model-full",
        default="gpt-5.4 high",
        help="Full model description shown in footer second line.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project name shown in footer (defaults to current directory name).",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Path to a real Codex terminal log file to replay instead of fake logs.",
    )
    parser.add_argument(
        "--bottom-interval",
        type=float,
        default=6.0,
        help="Seconds between bottom log updates (default: 6.0).",
    )
    parser.add_argument(
        "--follow-log-scroll",
        dest="follow_log_scroll",
        action="store_true",
        help="Make the novel pane auto-scroll down with each bottom log update.",
    )
    parser.add_argument(
        "--no-follow-log-scroll",
        dest="follow_log_scroll",
        action="store_false",
        help="Keep the novel pane independent from bottom log updates.",
    )
    parser.set_defaults(follow_log_scroll=False)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    book_path = Path(args.book).expanduser().resolve() if args.book else None
    log_path = Path(args.log).expanduser().resolve() if args.log else None
    cwd = Path.cwd()
    app = CodeNovelApp(
        book_path=book_path,
        task_title=args.title,
        model_name=args.model,
        model_provider=args.provider,
        model_full=args.model_full,
        project_name=args.project or cwd.name,
        project_path=str(cwd),
        log_path=log_path,
        bottom_interval=args.bottom_interval,
        follow_log_scroll=args.follow_log_scroll,
    )
    app.run()
