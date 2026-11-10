"""Find JavaScript and TypeScript comments without treating strings as comments."""

from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree

_TYPESCRIPT = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())
_BROKEN = frozenset({"ERROR", "MISSING"})


def scan_comments(
    source: str, *, jsx: bool
) -> tuple[int | None, list[tuple[int, str]]]:
    encoded = source.encode()
    language = _TSX if jsx else _TYPESCRIPT
    tree = Parser(language).parse(encoded)
    return _read_tree(tree, encoded)


def _read_tree(tree: Tree, encoded: bytes) -> tuple[int | None, list[tuple[int, str]]]:
    found: list[tuple[int, str]] = []
    cursor = tree.walk()
    walking = True
    while walking:
        node = cursor.node
        if node is not None and _broken(node):
            return node.start_point[0] + 1, []
        if node is not None and node.type == "comment":
            text = encoded[node.start_byte : node.end_byte].decode()
            found.append((node.start_point[0] + 1, text))
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                walking = False
                break
    if tree.root_node.has_error:
        return 1, []
    return None, found


def _broken(node: Node) -> bool:
    return node.is_error or node.is_missing or node.type in _BROKEN
