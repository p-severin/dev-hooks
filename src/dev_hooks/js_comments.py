"""Find JavaScript and TypeScript comments without treating strings as comments."""

from __future__ import annotations

_REGEX_KEYWORDS = frozenset(
    {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "new",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }
)
_REGEX_BEFORE = set("([{:;,=!?&|+-*%^~<>")


class _Frame:
    def __init__(self, kind: str, depth: int = 0) -> None:
        self.kind = kind
        self.depth = depth
        self.char_class = False


class _Scanner:
    def __init__(self, source: str) -> None:
        self.source = source
        self.index = 0
        self.line = 1
        self.frames = [_Frame("code")]
        self.can_regex = True
        self.found: list[tuple[int, str]] = []

    def scan(self) -> list[tuple[int, str]]:
        while self.index < len(self.source):
            kind = self.frames[-1].kind
            if kind in {"sq", "dq", "template"}:
                self._string()
            elif kind == "regex":
                self._regex()
            elif kind == "jsx_tag":
                self._jsx_tag()
            elif kind == "jsx_text":
                self._jsx_text()
            else:
                self._code()
        return self.found

    def _char(self) -> str:
        return self.source[self.index]

    def _nxt(self) -> str:
        if self.index + 1 < len(self.source):
            return self.source[self.index + 1]
        return ""

    def _at(self, offset: int) -> str:
        position = self.index + offset
        if position < len(self.source):
            return self.source[position]
        return ""

    def _newline(self) -> None:
        self.line += 1
        self.index += 1

    def _string(self) -> None:
        frame = self.frames[-1]
        char = self._char()
        nxt = self._nxt()
        if char == "\n":
            self._newline()
            return
        if char == "\\":
            self._escaped()
            return
        if frame.kind == "template" and char == "$" and nxt == "{":
            self.frames.append(_Frame("code", depth=1))
            self.index += 2
            self.can_regex = True
            return
        if frame.kind == "template" and char == "`":
            self.frames.pop()
            self.index += 1
            self.can_regex = False
            return
        quote = "'" if frame.kind == "sq" else '"'
        if frame.kind != "template" and char == quote:
            self.frames.pop()
            self.index += 1
            self.can_regex = False
            return
        self.index += 1

    def _escaped(self) -> None:
        nxt = self._nxt()
        if nxt == "\n":
            self.line += 1
            self.index += 2
            return
        if nxt == "\r" and self._at(2) == "\n":
            self.line += 1
            self.index += 3
            return
        self.index += 2

    def _regex(self) -> None:
        frame = self.frames[-1]
        char = self._char()
        if char == "\n":
            self.frames.pop()
            self._newline()
            return
        if char == "\\":
            self._escaped()
            return
        if frame.char_class:
            if char == "]":
                frame.char_class = False
            self.index += 1
            return
        if char == "[":
            frame.char_class = True
            self.index += 1
            return
        if char == "/":
            self.frames.pop()
            self.index += 1
            while self.index < len(self.source) and self.source[self.index].isalpha():
                self.index += 1
            self.can_regex = False
            return
        self.index += 1

    def _jsx_tag(self) -> None:
        char = self._char()
        nxt = self._nxt()
        if char == "\n":
            self._newline()
            return
        if char in {"'", '"'}:
            self.frames.append(_Frame("sq" if char == "'" else "dq"))
            self.index += 1
            return
        if char == "/" and nxt == ">":
            self.frames.pop()
            self.index += 2
            self.can_regex = False
            return
        if char == ">":
            self.frames[-1].kind = "jsx_text"
            self.index += 1
            return
        self.index += 1

    def _jsx_text(self) -> None:
        char = self._char()
        nxt = self._nxt()
        if char == "\n":
            self._newline()
            return
        if char == "{":
            self.frames.append(_Frame("code", depth=1))
            self.index += 1
            self.can_regex = True
            return
        if char == "<" and self._starts_tag(nxt):
            if nxt == "/":
                self._close_jsx()
                return
            self.frames.append(_Frame("jsx_tag"))
            self.index += 1
            return
        self.index += 1

    def _close_jsx(self) -> None:
        end = self.source.find(">", self.index)
        if end == -1:
            self.index = len(self.source)
            return
        self.line += self.source.count("\n", self.index, end)
        self.index = end + 1
        if self.frames[-1].kind == "jsx_text":
            self.frames.pop()

    def _code(self) -> None:
        char = self._char()
        nxt = self._nxt()
        if char == "\n":
            self._newline()
            self.can_regex = True
            return
        if char in " \t\r":
            self.index += 1
            return
        if char == "/" and nxt == "/" and not self._url_slash():
            self._line_comment()
            return
        if char == "/" and nxt == "*":
            self._block_comment()
            return
        if char == "/" and self.can_regex:
            self.frames.append(_Frame("regex"))
            self.index += 1
            return
        if char == "<" and self.can_regex and self._starts_tag(nxt):
            self.frames.append(_Frame("jsx_tag"))
            self.index += 1
            return
        if char in {"'", '"'}:
            self.frames.append(_Frame("sq" if char == "'" else "dq"))
            self.index += 1
            return
        if char == "`":
            self.frames.append(_Frame("template"))
            self.index += 1
            return
        if char == "{":
            self._open_brace()
            return
        if char == "}":
            self._close_brace()
            return
        if self._word_or_number():
            return
        self.index += 1
        if char in _REGEX_BEFORE:
            self.can_regex = True
        elif char in {")", "]"}:
            self.can_regex = False

    def _open_brace(self) -> None:
        frame = self.frames[-1]
        if len(self.frames) > 1 or frame.depth > 0:
            frame.depth += 1
        self.index += 1
        self.can_regex = True

    def _close_brace(self) -> None:
        frame = self.frames[-1]
        self.index += 1
        if frame.depth <= 0:
            return
        frame.depth -= 1
        self.can_regex = False
        if frame.depth == 0 and len(self.frames) > 1:
            self.frames.pop()

    def _word_or_number(self) -> bool:
        char = self._char()
        if char.isalpha() or char in {"_", "$"}:
            start = self.index
            self.index += 1
            while self.index < len(self.source) and (
                self.source[self.index].isalnum()
                or self.source[self.index] in {"_", "$"}
            ):
                self.index += 1
            self.can_regex = self.source[start : self.index] in _REGEX_KEYWORDS
            return True
        if char.isdigit():
            self.index += 1
            while self.index < len(self.source) and (
                self.source[self.index].isalnum()
                or self.source[self.index] in {".", "_"}
            ):
                self.index += 1
            self.can_regex = False
            return True
        return False

    def _starts_tag(self, nxt: str) -> bool:
        if nxt.isalpha() or nxt in {"_", ">"}:
            return True
        return nxt == "/" and self._at(2).isalpha()

    def _url_slash(self) -> bool:
        return self.index > 0 and self.source[self.index - 1] == ":"

    def _line_comment(self) -> None:
        end = self.source.find("\n", self.index)
        if end == -1:
            self.found.append((self.line, self.source[self.index :]))
            self.index = len(self.source)
            return
        self.found.append((self.line, self.source[self.index : end]))
        self.index = end

    def _block_comment(self) -> None:
        end = self.source.find("*/", self.index + 2)
        if end == -1:
            text = self.source[self.index :]
            self.found.append((self.line, text))
            self.line += text.count("\n")
            self.index = len(self.source)
            return
        text = self.source[self.index : end + 2]
        self.found.append((self.line, text))
        self.line += text.count("\n")
        self.index = end + 2


def scan_comments(source: str) -> list[tuple[int, str]]:
    return _Scanner(source).scan()
