"""Match repo-relative paths against hook globs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def compile_glob(pattern: str) -> re.Pattern[str]:
    pieces: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            pieces.append(r"(?:.*/)?")
            index += 3
            continue
        if pattern.startswith("**", index):
            pieces.append(".*")
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            pieces.append(r"[^/]*")
        elif char == "?":
            pieces.append(r"[^/]")
        else:
            pieces.append(re.escape(char))
        index += 1
    return re.compile("".join(pieces) + r"\Z")


def compile_globs(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(compile_glob(pattern) for pattern in patterns)


def normalize(path: str) -> str:
    return path.replace("\\", "/")


def matches(path: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    relative = normalize(path)
    return any(pattern.fullmatch(relative) for pattern in patterns)


def relative_of(path: Path, root: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return normalize(candidate.as_posix())
