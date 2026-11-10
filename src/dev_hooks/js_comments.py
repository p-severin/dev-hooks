"""Find JavaScript and TypeScript comments without treating strings as comments."""

from __future__ import annotations


def scan_comments(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    index = 0
    line = 1
    limit = len(source)
    stack = ["code"]
    while index < limit:
        state = stack[-1]
        char = source[index]
        nxt = source[index + 1] if index + 1 < limit else ""
        if char == "\n":
            line += 1
            index += 1
            continue
        if state in {"sq", "dq", "template"}:
            index = _skip_string_char(source, index, state, stack)
            continue
        index, line = _code_step(source, index, line, char, nxt, stack, found)
    return found


def _skip_string_char(source: str, index: int, state: str, stack: list[str]) -> int:
    char = source[index]
    nxt = source[index + 1] if index + 1 < len(source) else ""
    if char == "\\":
        return index + 2
    if state == "template" and char == "$" and nxt == "{":
        stack.append("code")
        return index + 2
    if state == "template" and char == "`":
        stack.pop()
        return index + 1
    quote = "'" if state == "sq" else '"'
    if state != "template" and char == quote:
        stack.pop()
    return index + 1


def _code_step(
    source: str,
    index: int,
    line: int,
    char: str,
    nxt: str,
    stack: list[str],
    found: list[tuple[int, str]],
) -> tuple[int, int]:
    if char == "/" and nxt == "/" and not _url_slash(source, index):
        return _take_line_comment(source, index, line, found)
    if char == "/" and nxt == "*":
        return _take_block_comment(source, index, line, found)
    if char == "'":
        stack.append("sq")
        return index + 1, line
    if char == '"':
        stack.append("dq")
        return index + 1, line
    if char == "`":
        stack.append("template")
        return index + 1, line
    if char == "}" and len(stack) > 1 and stack[-2] == "template":
        stack.pop()
    return index + 1, line


def _url_slash(source: str, index: int) -> bool:
    return index > 0 and source[index - 1] == ":"


def _take_line_comment(
    source: str,
    index: int,
    line: int,
    found: list[tuple[int, str]],
) -> tuple[int, int]:
    end = source.find("\n", index)
    if end == -1:
        found.append((line, source[index:]))
        return len(source), line
    found.append((line, source[index:end]))
    return end, line


def _take_block_comment(
    source: str,
    index: int,
    line: int,
    found: list[tuple[int, str]],
) -> tuple[int, int]:
    end = source.find("*/", index + 2)
    if end == -1:
        text = source[index:]
        found.append((line, text))
        return len(source), line + text.count("\n")
    text = source[index : end + 2]
    found.append((line, text))
    return end + 2, line + text.count("\n")
