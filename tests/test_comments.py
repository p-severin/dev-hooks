from pathlib import Path

from dev_hooks.comments import check_source, main


def test_docstring_and_hash_inside_a_string_are_allowed() -> None:
    source = '"""Note # not a comment."""\nvalue = "hash # inside"\n'
    assert check_source(source, relative="mod.py") == []


def test_plain_comment_reports_the_line() -> None:
    source = "value = 1\n# plain\n"
    assert check_source(source, relative="mod.py") == ["mod.py:2: plain comment"]


def test_inline_plain_comment_reports_the_line() -> None:
    source = "value = 1  # plain\n"
    assert check_source(source, relative="mod.py") == ["mod.py:1: plain comment"]


def test_every_plain_comment_is_reported() -> None:
    source = "# one\nvalue = 1  # two\n"
    assert check_source(source, relative="mod.py") == [
        "mod.py:1: plain comment",
        "mod.py:2: plain comment",
    ]


def test_tool_directives_are_allowed() -> None:
    source = """\
import sys  # noqa: F401
value = 1  # type: ignore[attr-defined]
other = 2  # pyright: ignore[reportUnusedVariable]
third = 3  # pragma: no cover
sixth = 6  # noqa: TC002 # runtime annotation
"""
    assert check_source(source, relative="mod.py") == []


def test_formatter_and_linter_directives_are_allowed() -> None:
    source = """\
# fmt: off
items = [1, 2]  # fmt: skip
# fmt: on
# ruff: noqa
# ruff: noqa: E501
# isort: skip
# isort: off
# pylint: disable=missing-docstring
"""
    assert check_source(source, relative="mod.py") == []
    assert check_source(source, relative="types.pyi") == []


def test_javascript_directives_are_plain_comments() -> None:
    source = """\
value = 1  # eslint-disable-next-line no-alert
other = 2  # @ts-expect-error sample
"""
    assert check_source(source, relative="mod.py") == [
        "mod.py:1: plain comment",
        "mod.py:2: plain comment",
    ]


def test_pyi_body_is_scanned() -> None:
    assert check_source("value: int  # plain\n", relative="types.pyi") == [
        "types.pyi:1: plain comment"
    ]


def test_directive_lookalikes_are_plain_comments() -> None:
    source = """\
# noqaish
# type: ignored
# pyright ignore
# pragma no cover
# see the noqa above
"""
    messages = check_source(source, relative="mod.py")
    assert [message.split(":")[1] for message in messages] == ["1", "2", "3", "4", "5"]


def test_shebang_and_whole_line_coding_cookie_are_allowed() -> None:
    source = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nvalue = 1\n"
    assert check_source(source, relative="mod.py") == []


def test_coding_cookie_on_line_two_is_allowed() -> None:
    source = "\n# coding: utf-8\n"
    assert check_source(source, relative="mod.py") == []


def test_inline_coding_cookie_is_a_plain_comment() -> None:
    source = "x = 1  # coding: utf-8 note\n"
    assert check_source(source, relative="mod.py") == ["mod.py:1: plain comment"]


def test_coding_word_without_a_cookie_is_a_plain_comment() -> None:
    source = "# coding style\n"
    assert check_source(source, relative="mod.py") == ["mod.py:1: plain comment"]


def test_coding_cookie_after_line_two_is_a_plain_comment() -> None:
    source = "x = 1\ny = 2\n# coding: utf-8\n"
    assert check_source(source, relative="mod.py") == ["mod.py:3: plain comment"]


def test_shebang_after_the_first_line_is_a_plain_comment() -> None:
    source = "x = 1\n#!/usr/bin/env python3\n"
    assert check_source(source, relative="mod.py") == ["mod.py:2: plain comment"]


def test_migration_revisions_are_excluded() -> None:
    source = "# generated\n"
    assert check_source(source, relative="app/migrations/versions/0001_init.py") == []
    assert check_source(source, relative="pkg/alembic/versions/0001_init.py") == []


def test_hand_written_migration_is_checked() -> None:
    source = "# keep\n"
    assert check_source(source, relative="app/migrations/hand_written.py") == [
        "app/migrations/hand_written.py:1: plain comment"
    ]


def test_generated_module_is_excluded() -> None:
    source = "# generated\n"
    assert check_source(source, relative="pkg/generated/models.py") == []
    assert check_source(source, relative="pkg/generated_notes.py") == [
        "pkg/generated_notes.py:1: plain comment"
    ]


def test_extra_exclude_skips_only_the_named_glob() -> None:
    source = "# note\n"
    assert check_source(source, relative="notes/a.py", excludes=("notes/**",)) == []
    assert check_source(source, relative="src/a.py", excludes=("notes/**",)) == [
        "src/a.py:1: plain comment"
    ]


def test_markdown_is_not_scanned() -> None:
    assert check_source("# Title\n", relative="README.md") == []


def test_unclosed_string_is_reported() -> None:
    messages = check_source('value = "open\n', relative="mod.py")
    assert len(messages) == 1
    assert messages[0].startswith("mod.py:")


def test_script_files_are_not_scanned() -> None:
    source = "const value = 1; // plain\n"
    assert check_source(source, relative="app.ts") == []
    assert check_source(source, relative="view.tsx") == []
    assert check_source(source, relative="app.js") == []


def test_comment_ban_hook_receives_python_files() -> None:
    text = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(".pre-commit-hooks.yaml")
        .read_text(encoding="utf-8")
    )
    block = text.split("id: comment-ban", maxsplit=1)[1].split("id:", maxsplit=1)[0]
    assert "types_or: [python, pyi]" in block
    assert "types: [file]" not in block


def test_cli_rejects_a_plain_comment(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("# plain\n", encoding="utf-8")
    assert main([str(target)]) == 1


def test_cli_accepts_a_file_without_comments(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("value = 1\n", encoding="utf-8")
    assert main([str(target)]) == 0
