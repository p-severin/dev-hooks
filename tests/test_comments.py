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
fourth = 4  # eslint-disable-next-line no-alert
fifth = 5  # @ts-expect-error sample
sixth = 6  # noqa: TC002 # runtime annotation
"""
    assert check_source(source, relative="mod.py") == []


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


def test_javascript_comment_is_rejected_and_string_is_kept() -> None:
    source = 'const url = "https://example.com";\nconst value = 1; // plain\n'
    assert check_source(source, relative="app.ts") == ["app.ts:2: plain comment"]


def test_javascript_block_comment_is_rejected() -> None:
    source = "const value = 1;\n/* plain */\n"
    assert check_source(source, relative="app.tsx") == ["app.tsx:2: plain comment"]


def test_javascript_directives_and_shebang_are_allowed() -> None:
    source = """\
#!/usr/bin/env node
const value = 1; // eslint-disable-next-line no-alert
// @ts-expect-error sample
const text = `not a // comment`;
const other = '/* still a string */';
"""
    assert check_source(source, relative="app.mjs") == []


def test_template_expression_comment_is_rejected() -> None:
    source = "const text = `value ${1 // plain\n}`;\n"
    assert check_source(source, relative="app.js") == ["app.js:1: plain comment"]


def test_regex_literal_and_jsx_text_are_not_comments() -> None:
    source = "const re = /https?:\\/\\//;\nconst node = <div>a//b</div>;\n"
    assert check_source(source, relative="view.tsx") == []


def test_comment_after_braces_inside_a_template_is_reported() -> None:
    source = "const text = `value ${ { a: 1 } // plain\n}`;\n"
    assert check_source(source, relative="app.ts") == ["app.ts:1: plain comment"]


def test_jsx_expression_comment_is_reported() -> None:
    source = "const node = <div>{1 // plain\n}</div>;\n"
    assert check_source(source, relative="view.tsx") == ["view.tsx:1: plain comment"]


def test_escaped_newline_in_a_string_advances_the_line() -> None:
    source = 'const value = "a\\\nb"; // plain\n'
    assert check_source(source, relative="app.ts") == ["app.ts:2: plain comment"]


def test_mts_and_cts_files_are_scanned() -> None:
    source = "const value = 1; // plain\n"
    assert check_source(source, relative="app.mts") == ["app.mts:1: plain comment"]
    assert check_source(source, relative="app.cts") == ["app.cts:1: plain comment"]


def test_comment_ban_hook_receives_every_file() -> None:
    text = (
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath(".pre-commit-hooks.yaml")
        .read_text(encoding="utf-8")
    )
    block = text.split("id: comment-ban", maxsplit=1)[1].split("id:", maxsplit=1)[0]
    assert "types: [file]" in block
    assert "types_or:" not in block


def test_cli_rejects_a_plain_comment(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("# plain\n", encoding="utf-8")
    assert main([str(target)]) == 1


def test_cli_accepts_a_file_without_comments(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("value = 1\n", encoding="utf-8")
    assert main([str(target)]) == 0


def test_comment_inside_a_jsx_opening_tag_is_reported() -> None:
    source = """\
export function Button(label: string) {
  return (
    <button
      className="row" // plain
    >
      {label}
    </button>
  );
}
"""
    assert check_source(source, relative="view.tsx") == ["view.tsx:4: plain comment"]


def test_comment_inside_a_jsx_attribute_expression_is_reported() -> None:
    source = '<div title={/* plain */ "x"} />\n'
    assert check_source(source, relative="view.tsx") == ["view.tsx:1: plain comment"]


def test_comparison_inside_a_jsx_attribute_does_not_end_the_tag() -> None:
    exact = "<Foo title={cond > 1 // plain"
    assert check_source(exact, relative="view.tsx") == [
        "view.tsx:1: cannot parse; comment check skipped"
    ]
    source = exact + "\n} />;\n// after\n"
    assert check_source(source, relative="view.tsx") == [
        "view.tsx:1: plain comment",
        "view.tsx:3: plain comment",
    ]


def test_fragment_text_is_not_a_comment_and_a_later_comment_is() -> None:
    source = "export const node = <>a//b</>;\n// plain\n"
    assert check_source(source, relative="view.tsx") == ["view.tsx:2: plain comment"]


def test_typescript_type_arguments_do_not_hide_a_later_comment() -> None:
    source = "export const id = <T>(value: T) => value;\n// plain\n"
    assert check_source(source, relative="app.ts") == ["app.ts:2: plain comment"]


def test_tsx_type_argument_with_a_comma_does_not_hide_a_later_comment() -> None:
    source = "export const id = <T,>(value: T) => value;\n// plain\n"
    assert check_source(source, relative="view.tsx") == ["view.tsx:2: plain comment"]


def test_type_assertion_does_not_hide_a_later_comment() -> None:
    source = "function f(value: string) {\n  return <string>value;\n}\n// plain\n"
    assert check_source(source, relative="app.ts") == ["app.ts:4: plain comment"]


def test_division_on_the_next_line_is_not_a_regex() -> None:
    source = "const value = y\n/ 2 // plain\n"
    assert check_source(source, relative="app.ts") == ["app.ts:2: plain comment"]


def test_regex_after_a_control_statement_is_not_a_comment() -> None:
    for statement in (
        "if (ok) /foo\\/\\//;",
        "while (ok) /foo\\/\\//;",
        "for (;;) /foo\\/\\//;",
        "with (ok) /foo\\/\\//;",
    ):
        assert check_source(statement + "\n", relative="app.ts") == []


def test_switch_without_a_block_fails_closed() -> None:
    source = "switch (ok) /foo\\/\\//;\n"
    assert check_source(source, relative="app.ts") == [
        "app.ts:1: cannot parse; comment check skipped"
    ]


def test_unclosed_block_comment_fails_closed() -> None:
    source = "const value = 1; /*\nplain\nstill\n"
    assert check_source(source, relative="src/unclosed.ts") == [
        "src/unclosed.ts:1: cannot parse; comment check skipped"
    ]


def test_html_comment_in_tsx_fails_closed() -> None:
    source = "const node = <div><!-- x --></div>;\nconst value = 1;\n// plain\n"
    assert check_source(source, relative="src/html.tsx") == [
        "src/html.tsx:1: cannot parse; comment check skipped"
    ]
