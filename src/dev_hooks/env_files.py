"""Reject secret env files and local settings."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from dev_hooks.globs import compile_globs, matches, relative_of
from dev_hooks.report import report

if TYPE_CHECKING:
    from collections.abc import Sequence

_SAFE_ENV_NAMES = frozenset({".env.example", ".env.sample"})


_SECRET_DIRS = frozenset({".env", "run.env", "secrets"})


def _folded(relative: str) -> str:
    return relative.replace("\\", "/").casefold()


def classify(relative: str) -> str | None:
    path = _folded(relative)
    parts = path.split("/")
    name = parts[-1]
    if any(part in _SECRET_DIRS for part in parts[:-1]):
        return "secret directory"
    if name in _SAFE_ENV_NAMES:
        return None
    if name == "run.env":
        return "run.env"
    if name == ".env" or _dotted_env(name):
        return "env file"
    if path == ".claude/settings.local.json" or path.endswith(
        "/.claude/settings.local.json"
    ):
        return "local settings file"
    return None


def _dotted_env(name: str) -> bool:
    return name.startswith(".env.") and name not in _SAFE_ENV_NAMES


def check_relative(
    relative: str,
    *,
    allow: Sequence[str] = (),
    deny: Sequence[str] = (),
) -> str | None:
    if _folded(relative).rsplit("/", 1)[-1] in _SAFE_ENV_NAMES and not _secret_dir(
        relative
    ):
        return None
    allowed = compile_globs(tuple(allow))
    if allow and matches(relative, allowed):
        return None
    denied = compile_globs(deny)
    if matches(relative, denied):
        return "denied path"
    return classify(relative)


def _secret_dir(relative: str) -> bool:
    parts = _folded(relative).split("/")
    return any(part in _SECRET_DIRS for part in parts[:-1])


def finding(relative: str, reason: str) -> str:
    return f"{relative}: do not commit this file ({reason})"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reject run.env, .env, .env.*, files under secrets/, "
            "and .claude/settings.local.json. .env.example and .env.sample stay."
        )
    )
    parser.add_argument(
        "paths", nargs="*", help="Files to check. With no paths, succeed."
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="Extra glob that may be committed. .env.example and .env.sample are always allowed.",
    )
    parser.add_argument(
        "--deny",
        action="append",
        default=[],
        help="Extra glob that may not be committed.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    findings: list[str] = []
    seen: set[str] = set()
    for raw in args.paths:
        relative = relative_of(Path(raw), root)
        if relative in seen:
            continue
        seen.add(relative)
        reason = check_relative(relative, allow=args.allow, deny=args.deny)
        if reason is not None:
            findings.append(finding(relative, reason))
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
