"""Reject code comments in Python."""

from __future__ import annotations

import argparse
import io
import re
import sys
import tokenize
from pathlib import Path
from typing import TYPE_CHECKING

from dev_hooks.globs import compile_globs, matches, relative_of
from dev_hooks.report import report

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_EXCLUDES: tuple[str, ...] = (
    "**/migrations/versions/**",
    "**/alembic/versions/**",
    "**/generated/**",
)

_PYTHON = frozenset({".py", ".pyi"})
_DIRECTIVE = re.compile(
    r"^(?:noqa(?:\s|:|$)|type:\s*ignore\b|pyright:|pragma:|fmt:|ruff:|isort:|pylint:)"
)
_PEP263 = re.compile(r"coding[:=][ \t]*[-_.a-zA-Z0-9]+")
_WHOLE_HASH_LINE = re.compile(r"^[ \t\f]*#")


def comment_body(text: str) -> str:
    if text.startswith("#"):
        return text[1:].strip()
    return text.strip()


def directive_allowed(text: str) -> bool:
    return _DIRECTIVE.match(comment_body(text)) is not None


def coding_cookie(line_text: str, line_no: int) -> bool:
    if line_no > 2 or not _WHOLE_HASH_LINE.match(line_text):
        return False
    return _PEP263.search(line_text) is not None


def python_findings(source: str, relative: str) -> list[str]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        lines = source.splitlines()
        return [
            f"{relative}:{token.start[0]}: plain comment"
            for token in tokens
            if token.type == tokenize.COMMENT
            and not _python_allowed(token.string, token.start[0], lines)
        ]
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        return [f"{relative}: {exc}"]


def _python_allowed(text: str, line_no: int, lines: Sequence[str]) -> bool:
    if line_no == 1 and text.startswith("#!"):
        return True
    line_text = lines[line_no - 1] if 1 <= line_no <= len(lines) else text
    if coding_cookie(line_text, line_no):
        return True
    return directive_allowed(text)


def check_source(
    source: str,
    *,
    relative: str,
    excludes: Sequence[str] = (),
) -> list[str]:
    patterns = compile_globs(DEFAULT_EXCLUDES + tuple(excludes))
    if matches(relative, patterns):
        return []
    suffix = Path(relative).suffix.lower()
    if suffix in _PYTHON:
        return python_findings(source, relative)
    return []


def check_path(path: Path, root: Path, excludes: Sequence[str]) -> list[str]:
    relative = relative_of(path, root)
    candidate = path if path.is_absolute() else root / path
    suffix = Path(relative).suffix.lower()
    if suffix not in _PYTHON:
        return []
    if not candidate.is_file():
        return [f"{relative}: not a file"]
    try:
        source = _read(candidate)
    except (OSError, SyntaxError, UnicodeError) as exc:
        return [f"{relative}: {exc}"]
    return check_source(source, relative=relative, excludes=excludes)


def _read(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reject code comments in Python. Docstrings stay. Tool directives, "
            "a shebang, and a whole-line coding cookie stay."
        )
    )
    parser.add_argument(
        "paths", nargs="*", help="Files to check. With no paths, succeed."
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Extra glob skipped in addition to migrations and generated files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        findings: list[str] = []
        for path in args.paths:
            findings.extend(check_path(Path(path), root, args.exclude))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
