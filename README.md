# Add the shared hooks

Use this repo when a Python project should run the same pre-commit checks as the others. You add one `repo` entry and pin `rev`. Pass `args` only for the limits, globs, and allow lists that belong to that repo. Leave hooks that are specific to one service in that repo.

## Add the config

Replace `pin-this-to-a-commit` with the full commit SHA or tag you want to run.

```yaml
repos:
  - repo: https://github.com/p-severin/dev-hooks
    rev: pin-this-to-a-commit
    hooks:
      - id: file-token-limit
      - id: comment-ban
      - id: pii-fixtures
      - id: forbid-env-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: 0.13.7
    hooks:
      - id: uv-lock

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.9.0
    hooks:
      - id: gitleaks

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: detect-private-key
      - id: debug-statements
      - id: check-merge-conflict
      - id: check-case-conflict
      - id: check-added-large-files
        args: ["--maxkb=1024"]
        exclude: '(^|/)fixtures/.*\.(html|htm)$'
      - id: trailing-whitespace
        exclude: '(^|/)fixtures/.*\.(html|htm)$'
      - id: end-of-file-fixer
        exclude: '(^|/)fixtures/.*\.(html|htm)$'
      - id: mixed-line-ending
        args: ["--fix=lf"]
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-ast
```

In CI, run:

```bash
pre-commit run --all-files
```

The gitleaks hook from that repo runs `gitleaks protect --staged`. A commit scans staged changes. On a clean checkout, `pre-commit run --all-files` does not scan older git history. `detect-private-key` still checks the files pre-commit passes.

`check-added-large-files` allows files up to 1024 KB and skips HTML fixtures. `end-of-file-fixer` and `trailing-whitespace` skip those fixtures too, because captured pages often have trailing spaces.

## Extend the Ruff config

Copy `ruff.shared.toml` into the consumer repo. Ruff `extend` reads a file path. It does not fetch this git repo.

```toml
[tool.ruff]
extend = "ruff.shared.toml"
```

The shared file adds three rules on top of the rules you already select.

`C901` fails a function whose cyclomatic complexity is above 15. `E722` fails a bare `except`. `BLE001` fails `except Exception`.

An existing violation stays out of the build when you name the file and the code. Do not ignore a code for the whole repo.

```toml
[tool.ruff.lint.per-file-ignores]
"src/legacy_parser.py" = ["C901"]
"src/old_client.py" = ["E722", "BLE001"]
```

## file-token-limit

The count is `ceil(bytes / 4)`. The default limit is 5000.

A path missing from the baseline fails when the count is over the limit. A path present in the baseline fails when the count is over the recorded number. The file may shrink. It may not grow. A recorded count under 5000 is still that file's ceiling.

Pre-commit passes staged paths on commit. `pre-commit run --all-files` passes every tracked file. The hook checks the paths it receives.

`--limit` sets the ceiling for a path that is not in the baseline. The default is `5000`.

`--baseline` is a JSON object of repo-relative path to token count. The default path is `.file-token-baseline.json`. The file must exist when the hook has a path to check. An empty object is valid.

`--exclude` adds a glob. The hook already skips lockfiles, paths under `generated`, migration revisions in `migrations/versions` and `alembic/versions`, and `*_pb2.py` modules.

The error tells you how to split the file. For Markdown it tells you to link sub-documents.

```json
{
  "src/app.py": 6200
}
```

## comment-ban

The hook rejects comments in Python and in JavaScript or TypeScript. Docstrings stay, because they are strings.

A comment stays when its text starts with `noqa`, `type: ignore`, `pyright:`, `pragma:`, `eslint-disable`, or `@ts-`. A shebang on line 1 stays. A coding cookie stays only when all three are true. The comment is the whole line. The line is line 1 or line 2. The line matches PEP 263, which is `coding` followed by `:` or `=` and an encoding name. An inline note such as `x = 1  # coding: utf-8 note` fails.

Checked suffixes are `.py`, `.pyi`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, and `.cts`.

`--exclude` adds a glob. The hook already skips migration revisions, paths under `generated`, and `*.min.js`.

## pii-fixtures

The default globs are `tests/**`, `**/tests/**`, and `**/fixtures/**`.

The hook reports four kinds of hit.

An email is reported unless the domain is `example.com`, `example.org`, `example.net`, `example.edu`, `localhost`, `invalid`, or `test`, or the domain ends in `.example`, `.invalid`, `.test`, or `.localhost`.

A PESEL is an 11-digit number with a real date and a valid checksum.

A phone is a `+` number, a `00` international number, or a number on a line that contains `phone`, `telefon`, `tel`, or `mobile`. A number whose last nine digits are all the same is ignored.

A name is a listed first name followed by a capitalized surname. A value on `name`, `first_name`, `last_name`, `full_name`, `imię`, `imie`, or `nazwisko` is also a name when it starts with a listed first name. `Jane Doe` is ignored. A single capitalized word in ordinary prose is ignored.

A line that contains the token `pii-ok` is ignored. `--allowlist` points at a text file with one regular expression per line. A blank line is ignored. A line that starts with `#` is ignored. A finding whose text matches a line is ignored.

`--glob`, when set, replaces the default globs. Repeat it for more than one glob. `--exclude` skips a glob after the include list matches.

Street addresses are not detected. A street line matches too much ordinary text.

## forbid-env-files

The hook rejects `run.env`, `.env`, any `.env.*` file, and `.claude/settings.local.json`. It also rejects a path whose directory is named `.env`, `run.env`, or `secrets`. Matching ignores case. `.env.example` and `.env.sample` stay allowed.

`.env.example` and `.env.sample` are allowed. `--allow` adds an allow glob. `--deny` adds a deny glob. An allow match wins over a deny match.

## What you still keep in the consumer repo

Keep `.file-token-baseline.json` in the repo. This hook reads it and does not write it.

Keep any CI that publishes a lower baseline, reads a pull request label, or classifies `github.event.before`. Those steps know the repo's branches and labels. This repo does not ship them.

Keep a same-commit guard if you still want to stop a baseline count from rising in the commit that grows the file. This hook treats the baseline it reads as the ceiling. It does not compare that file with `HEAD`.

Keep exclude globs that are specific to one repo, and keep local hooks that are not these four.
