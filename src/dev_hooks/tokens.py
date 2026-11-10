"""Reject files that exceed a token limit or their baseline count."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dev_hooks.globs import compile_globs, matches, relative_of
from dev_hooks.report import report

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

BYTES_PER_TOKEN = 4
DEFAULT_LIMIT = 5_000
DEFAULT_BASELINE = ".file-token-baseline.json"

DEFAULT_EXCLUDES: tuple[str, ...] = (
    "**/uv.lock",
    "**/poetry.lock",
    "**/Pipfile.lock",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
    "**/yarn.lock",
    "**/bun.lock",
    "**/npm-shrinkwrap.json",
    "**/shrinkwrap.yaml",
    "**/packages.lock.json",
    "**/Cargo.lock",
    "**/Gemfile.lock",
    "**/composer.lock",
    "**/go.sum",
    "**/pdm.lock",
    "**/flake.lock",
    "**/generated/**",
    "**/migrations/versions/**",
    "**/alembic/versions/**",
    "**/*_pb2.py",
    "**/*_pb2.pyi",
    "**/*_pb2_grpc.py",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.ico",
    "**/*.pdf",
    "**/*.zip",
    "**/*.gz",
    "**/*.woff",
    "**/*.woff2",
    "**/*.wasm",
)

_CODE_ADVICE = (
    "Split this file by responsibility.",
    "Keep one cohesive concept per module, in the same package.",
    "Re-export from the package __init__ when callers need a stable import.",
    "Move a large constant table into a data file next to the module.",
    "Split a large test file per feature.",
    "Keep shared helpers in an existing shared module.",
    "Do not minify, compress whitespace, or join lines to get under the limit.",
    "Do not edit the baseline to hide this growth.",
)

_MARKDOWN_ADVICE = (
    "Split this Markdown file into linked sub-documents.",
    "Keep this file as a short entry point and link each section.",
    "Move a long section into a sibling file in the same directory.",
    "Point the entry point at that sibling with a relative link.",
    "Do not minify, compress whitespace, or join lines to get under the limit.",
    "Do not edit the baseline to hide this growth.",
)


def token_count(num_bytes: int) -> int:
    return (num_bytes + BYTES_PER_TOKEN - 1) // BYTES_PER_TOKEN


def parse_baseline(text: str, label: str) -> dict[str, int]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        message = f"{label} is not valid JSON: {exc}"
        raise ValueError(message) from exc
    if not isinstance(data, dict):
        message = f"{label} must be a JSON object of path to token count"
        raise TypeError(message)
    baseline: dict[str, int] = {}
    for key, value in data.items():
        _reject_bad_entry(label, key, value)
        baseline[key.replace("\\", "/")] = value
    return baseline


def _reject_bad_entry(label: str, key: object, value: object) -> None:
    if not isinstance(key, str) or not _valid_key(key):
        message = f"{label} entry {key!r} must be a relative path"
        raise ValueError(message)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        message = f"{label} entry {key!r} must map a path to a non-negative integer"
        raise ValueError(message)


def _valid_key(key: str) -> bool:
    if key == "" or key.startswith(("/", "../")) or "\\" in key:
        return False
    return ".." not in Path(key).parts


def load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        message = (
            f"{path.as_posix()} is not in the tree.\n"
            "Add this file. An empty object {} is allowed.\n"
            "A recorded count is the ceiling for that path, "
            "even when the count is under the limit."
        )
        raise ValueError(message)
    return parse_baseline(path.read_text(encoding="utf-8"), path.as_posix())


def split_advice(relative: str) -> str:
    lines = (
        _MARKDOWN_ADVICE if relative.endswith((".md", ".markdown")) else _CODE_ADVICE
    )
    return "\n".join(lines)


def over_limit_message(
    relative: str,
    tokens: int,
    allowed: int,
    limit: int,
    *,
    from_baseline: bool,
) -> str:
    if from_baseline:
        header = (
            f"{relative} has {tokens} tokens, above its baseline of "
            f"{allowed} (limit {limit})."
        )
    else:
        header = f"{relative} has {tokens} tokens (limit {limit})."
    return f"{header}\n{split_advice(relative)}"


def check_file(
    candidate: Path,
    relative: str,
    baseline: Mapping[str, int],
    limit: int,
) -> list[str]:
    if not candidate.is_file():
        return [f"{relative}: not a file"]
    data = candidate.read_bytes()
    if b"\0" in data:
        return []
    tokens = token_count(len(data))
    recorded = baseline.get(relative)
    allowed = limit if recorded is None else recorded
    if tokens <= allowed:
        return []
    return [
        over_limit_message(
            relative,
            tokens,
            allowed,
            limit,
            from_baseline=recorded is not None,
        )
    ]


def check_paths(
    paths: Sequence[Path],
    *,
    root: Path,
    baseline_path: Path,
    limit: int,
    excludes: Sequence[str] = (),
) -> list[str]:
    if not paths:
        return []
    baseline = load_baseline(baseline_path)
    patterns = compile_globs(DEFAULT_EXCLUDES + tuple(excludes))
    baseline_relative = relative_of(baseline_path, root)
    findings: list[str] = []
    seen: set[str] = set()
    for path in paths:
        relative = relative_of(path, root)
        if relative in seen:
            continue
        seen.add(relative)
        if relative == baseline_relative or matches(relative, patterns):
            continue
        candidate = path if path.is_absolute() else root / path
        findings.extend(check_file(candidate, relative, baseline, limit))
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reject a new file over the token limit, and reject an existing "
            "file that grows past its baseline count."
        )
    )
    parser.add_argument(
        "paths", nargs="*", help="Files to check. With no paths, succeed."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Token ceiling for a path that is not in the baseline (default {DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE,
        help=f"JSON object of repo-relative path to token count (default {DEFAULT_BASELINE}).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Extra glob skipped in addition to lockfiles, generated code, and migrations.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be a positive integer")
    root = Path.cwd()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    try:
        findings = check_paths(
            [Path(path) for path in args.paths],
            root=root,
            baseline_path=baseline_path,
            limit=args.limit,
            excludes=args.exclude,
        )
    except (TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
