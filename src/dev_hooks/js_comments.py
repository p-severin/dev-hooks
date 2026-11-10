"""Find JavaScript and TypeScript comments without treating strings as comments."""

from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree

_TYPESCRIPT = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())
_KEPT = frozenset({"comment", "html_comment"})


def scan_comments(source: str, *, jsx: bool) -> tuple[list[int], list[tuple[int, str]]]:
    encoded = source.encode()
    language = _TSX if jsx else _TYPESCRIPT
    tree = Parser(language).parse(encoded)
    return _read_tree(tree, encoded)


def _read_tree(tree: Tree, encoded: bytes) -> tuple[list[int], list[tuple[int, str]]]:
    found: list[tuple[int, str]] = []
    hidden: list[int] = []
    cursor = tree.walk()
    walking = True
    while walking:
        node = cursor.node
        if node is not None:
            _take(node, encoded, found, hidden)
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                walking = False
                break
    return _unique(hidden), found


def _take(
    node: Node,
    encoded: bytes,
    found: list[tuple[int, str]],
    hidden: list[int],
) -> None:
    if node.type in _KEPT:
        text = encoded[node.start_byte : node.end_byte].decode()
        found.append((node.start_point[0] + 1, text))
        return
    if node.type == "ERROR" or node.is_error:
        text = encoded[node.start_byte : node.end_byte].decode()
        if text.startswith("/*") and "*/" not in text:
            hidden.append(node.start_point[0] + 1)
        return
    if node.type == "jsx_text" and _inside_error(node):
        hidden.extend(_line_comments(node, encoded))


def _inside_error(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "ERROR" or parent.is_error:
            return True
        parent = parent.parent
    return False


def _line_comments(node: Node, encoded: bytes) -> list[int]:
    text = encoded[node.start_byte : node.end_byte].decode()
    start = node.start_point[0] + 1
    lines: list[int] = []
    for offset, line in enumerate(text.split("\n")):
        stripped = line.lstrip(" \t")
        if stripped.startswith(("//", "/*")):
            lines.append(start + offset)
    return lines


def _unique(lines: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        ordered.append(line)
    return ordered
