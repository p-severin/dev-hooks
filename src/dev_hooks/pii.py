"""Reject likely personal data in tests and fixtures."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from dev_hooks.globs import compile_globs, matches, relative_of
from dev_hooks.names import FIRST_NAMES, PLACEHOLDER_SURNAMES, SURNAME_STOP
from dev_hooks.report import report

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_GLOBS: tuple[str, ...] = ("tests/**", "**/tests/**", "**/fixtures/**")
_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_E164 = re.compile(r"(?<!\w)\+(?:\d[ \t.\-()]?){7,14}\d(?!\d)")
_INTL00 = re.compile(r"(?<!\d)00(?:[ \t.\-]?\d){8,15}(?!\d)")
_LABELED_PHONE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:phone|telefon|mobile|komórka|komorka|tel)"
    r"(?![A-Za-z0-9_]).{0,40}?(\+?\d(?:[ \t.\-()]?\d){7,14})"
)
_PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
_PAIR = re.compile(
    r"(?<![A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])"
    r"([A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,})"
    r"[ \t]+"
    r"([A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]{2,})"
    r"(?![A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])"
)
_LABEL = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:first_name|last_name|full_name|given_name|family_name|"
    r"firstName|lastName|fullName|contact_name|contactName|"
    r"imię|imie|nazwisko|name)"
    r"(?![A-Za-z0-9_])"
    r"""\s*["']?\s*[:=]\s*["']?"""
    r"([A-ZŁŚŻŹĆŃÓ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż.\-]*(?:[ \t]+[A-ZŁŚŻŹĆŃÓ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż.\-]*)?)"
)
_PII_OK = re.compile(r"(?<![\w-])pii-ok(?![\w-])")
_SKIP_DOMAINS = frozenset(
    {
        "example.com",
        "example.org",
        "example.net",
        "example.edu",
        "invalid",
        "localhost",
        "test",
    }
)
_SKIP_SUFFIXES = (".example", ".invalid", ".test", ".localhost")

Span = tuple[int, int, str]


def pesel_ok(digits: str) -> bool:
    if len(digits) != 11 or not digits.isdigit() or not _pesel_date(digits):
        return False
    total = sum(int(digits[index]) * _WEIGHTS[index] for index in range(10))
    return (10 - (total % 10)) % 10 == int(digits[10])


def _pesel_date(digits: str) -> bool:
    year = int(digits[0:2])
    month = int(digits[2:4])
    day = int(digits[4:6])
    if 1 <= month <= 12:
        year += 1900
    elif 21 <= month <= 32:
        year += 2000
        month -= 20
    elif 41 <= month <= 52:
        year += 2100
        month -= 40
    elif 81 <= month <= 92:
        year += 1800
        month -= 80
    else:
        return False
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def check_text(
    source: str,
    *,
    relative: str,
    globs: Sequence[str] = DEFAULT_GLOBS,
    excludes: Sequence[str] = (),
    allow: Sequence[re.Pattern[str]] = (),
) -> list[str]:
    if not _selected(relative, globs, excludes):
        return []
    findings: list[str] = []
    seen: set[tuple[int, str, str]] = set()
    for line_no, line in enumerate(source.splitlines(), start=1):
        if _PII_OK.search(line):
            continue
        for kind, text in _line_hits(line):
            if _suppressed(text, allow):
                continue
            key = (line_no, kind, text)
            if key in seen:
                continue
            seen.add(key)
            findings.append(f"{relative}:{line_no}: {kind} {text}")
    return findings


def _selected(relative: str, globs: Sequence[str], excludes: Sequence[str]) -> bool:
    if not matches(relative, compile_globs(globs)):
        return False
    return not matches(relative, compile_globs(excludes))


def _suppressed(text: str, allow: Sequence[re.Pattern[str]]) -> bool:
    if text in {"REDACTED", "PLACEHOLDER"}:
        return True
    return any(pattern.search(text) for pattern in allow)


def _line_hits(line: str) -> list[tuple[str, str]]:
    emails = _email_spans(line)
    pesels = _pesel_spans(line)
    phones = _phone_spans(line, pesels)
    names = _name_spans(line, emails)
    return (
        _tagged("email", emails)
        + _tagged("pesel", pesels)
        + _tagged("phone", phones)
        + _tagged("name", names)
    )


def _tagged(kind: str, spans: Sequence[Span]) -> list[tuple[str, str]]:
    return [(kind, text) for _start, _end, text in spans]


def _email_spans(line: str) -> list[Span]:
    return [
        (match.start(), match.end(), match.group(0))
        for match in _EMAIL.finditer(line)
        if not _email_ignored(match.group(0))
    ]


def _email_ignored(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower().rstrip(".")
    if domain in _SKIP_DOMAINS:
        return True
    return any(domain.endswith(suffix) for suffix in _SKIP_SUFFIXES)


def _pesel_spans(line: str) -> list[Span]:
    return [
        (match.start(), match.end(), match.group(0))
        for match in _PESEL.finditer(line)
        if pesel_ok(match.group(0))
    ]


def _phone_spans(line: str, pesels: Sequence[Span]) -> list[Span]:
    found = (
        _pattern_spans(_E164, line)
        + _pattern_spans(_INTL00, line)
        + _labeled_phones(line)
    )
    kept: list[Span] = []
    seen: set[tuple[int, int]] = set()
    for start, end, text in found:
        if (
            (start, end) in seen
            or _placeholder_phone(text)
            or _overlaps(start, end, pesels)
        ):
            continue
        seen.add((start, end))
        kept.append((start, end, text))
    return kept


def _pattern_spans(pattern: re.Pattern[str], line: str) -> list[Span]:
    return [
        (match.start(), match.end(), match.group(0)) for match in pattern.finditer(line)
    ]


def _labeled_phones(line: str) -> list[Span]:
    found: list[Span] = []
    for match in _LABELED_PHONE.finditer(line):
        number = match.group(1)
        start = match.start(1)
        found.append((start, start + len(number), number))
    return found


def _placeholder_phone(text: str) -> bool:
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) < 8:
        return True
    tail = digits[-9:]
    return len(set(tail)) <= 1


def _name_spans(line: str, emails: Sequence[Span]) -> list[Span]:
    found: list[Span] = []
    for match in _PAIR.finditer(line):
        if not _pair_hit(match.group(1), match.group(2)):
            continue
        span = (match.start(), match.end(), match.group(0))
        if not _overlaps(span[0], span[1], emails):
            found.append(span)
    for match in _LABEL.finditer(line):
        value = match.group(1).strip()
        if not _labeled_name(value):
            continue
        span = (match.start(1), match.start(1) + len(value), value)
        if not _overlaps(span[0], span[1], emails):
            found.append(span)
    return found


def _pair_hit(first: str, second: str) -> bool:
    if first not in FIRST_NAMES:
        return False
    return second not in SURNAME_STOP and second not in PLACEHOLDER_SURNAMES


def _labeled_name(value: str) -> bool:
    parts = value.split()
    if not parts or parts[0] not in FIRST_NAMES:
        return False
    if len(parts) == 1:
        return True
    return parts[1] not in SURNAME_STOP and parts[1] not in PLACEHOLDER_SURNAMES


def _overlaps(start: int, end: int, spans: Sequence[Span]) -> bool:
    return any(
        start < span_end and end > span_start for span_start, span_end, _text in spans
    )


def load_allowlist(path: Path) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line))
        except re.error as exc:
            message = f"{path.as_posix()}:{line_no}: invalid regular expression: {exc}"
            raise ValueError(message) from exc
    return patterns


def check_path(
    path: Path,
    root: Path,
    *,
    globs: Sequence[str],
    excludes: Sequence[str],
    allow: Sequence[re.Pattern[str]],
) -> list[str]:
    relative = relative_of(path, root)
    if not _selected(relative, globs, excludes):
        return []
    candidate = path if path.is_absolute() else root / path
    if not candidate.is_file():
        return [f"{relative}: not a file"]
    data = candidate.read_bytes()
    if b"\0" in data:
        return []
    try:
        source = data.decode("utf-8")
    except UnicodeError:
        return []
    return check_text(
        source,
        relative=relative,
        globs=globs,
        excludes=excludes,
        allow=allow,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reject emails, phone numbers, PESEL numbers, and personal names "
            "in tests and fixtures."
        )
    )
    parser.add_argument(
        "paths", nargs="*", help="Files to check. With no paths, succeed."
    )
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        help="Glob to scan. Replaces the default tests and fixtures globs when set.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob to skip after the include globs match.",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help="File of regular expressions. A matching value is ignored.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    globs = tuple(args.glob) if args.glob else DEFAULT_GLOBS
    try:
        allow = load_allowlist(Path(args.allowlist)) if args.allowlist else []
        findings: list[str] = []
        for path in args.paths:
            findings.extend(
                check_path(
                    Path(path),
                    root,
                    globs=globs,
                    excludes=args.exclude,
                    allow=allow,
                )
            )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return report(findings)


if __name__ == "__main__":
    raise SystemExit(main())
