from pathlib import Path

import pytest

from dev_hooks.tokens import check_paths, main, token_count

BYTES = 4


def _blob(tokens: int) -> bytes:
    return b"a" * (tokens * BYTES)


def _write(root: Path, relative: str, tokens: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_blob(tokens))


def _baseline(root: Path, payload: str) -> Path:
    path = root / ".file-token-baseline.json"
    path.write_text(payload, encoding="utf-8")
    return path


def _check(
    root: Path,
    relative: str,
    *,
    limit: int = 5000,
    excludes: tuple[str, ...] = (),
) -> list[str]:
    return check_paths(
        [root / relative],
        root=root,
        baseline_path=root / ".file-token-baseline.json",
        limit=limit,
        excludes=excludes,
    )


def test_token_count_is_ceil_bytes_over_four() -> None:
    assert token_count(0) == 0
    assert token_count(1) == 1
    assert token_count(4) == 1
    assert token_count(5) == 2


def test_new_file_at_the_limit_passes(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "src/app.py", 5000)
    assert _check(tmp_path, "src/app.py") == []


def test_new_file_over_the_limit_explains_the_split(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "src/app.py", 5001)
    messages = _check(tmp_path, "src/app.py")
    assert len(messages) == 1
    assert "src/app.py has 5001 tokens (limit 5000)." in messages[0]
    assert "Split this file by responsibility." in messages[0]
    assert "Do not minify" in messages[0]
    assert "spider" not in messages[0]
    assert "car_scraping" not in messages[0]


def test_markdown_over_the_limit_says_to_link_subdocuments(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "docs/guide.md", 5001)
    messages = _check(tmp_path, "docs/guide.md")
    assert "linked sub-documents" in messages[0]


def test_only_the_given_file_is_checked(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "src/small.py", 10)
    _write(tmp_path, "src/huge.py", 5001)
    assert _check(tmp_path, "src/small.py") == []


def test_no_paths_succeeds_without_a_baseline(tmp_path: Path) -> None:
    assert (
        check_paths(
            [],
            root=tmp_path,
            baseline_path=tmp_path / "missing.json",
            limit=5000,
        )
        == []
    )


def test_recorded_count_under_the_limit_is_still_the_ceiling(tmp_path: Path) -> None:
    _baseline(tmp_path, '{"src/app.py": 100}\n')
    _write(tmp_path, "src/app.py", 100)
    assert _check(tmp_path, "src/app.py") == []
    _write(tmp_path, "src/app.py", 101)
    messages = _check(tmp_path, "src/app.py")
    assert "above its baseline of 100 (limit 5000)" in messages[0]
    assert "Split this file by responsibility." in messages[0]


def test_baseline_allows_the_same_size_and_a_shrink(tmp_path: Path) -> None:
    _baseline(tmp_path, '{"src/app.py": 8000}\n')
    _write(tmp_path, "src/app.py", 8000)
    assert _check(tmp_path, "src/app.py") == []
    _write(tmp_path, "src/app.py", 7000)
    assert _check(tmp_path, "src/app.py") == []


def test_baseline_rejects_growth_above_the_recorded_count(tmp_path: Path) -> None:
    _baseline(tmp_path, '{"src/app.py": 8000}\n')
    _write(tmp_path, "src/app.py", 8001)
    messages = _check(tmp_path, "src/app.py")
    assert "above its baseline of 8000 (limit 5000)" in messages[0]


def test_lockfile_codegen_and_migration_are_skipped(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    relatives = (
        "uv.lock",
        "pkg/generated/models.py",
        "app/migrations/versions/0001_init.py",
        "pkg/alembic/versions/0001_init.py",
        "src/models_pb2.py",
    )
    for relative in relatives:
        _write(tmp_path, relative, 5001)
        assert _check(tmp_path, relative) == []


def test_hand_written_migration_is_checked(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "app/migrations/hand_written.py", 5001)
    assert _check(tmp_path, "app/migrations/hand_written.py")


def test_extra_exclude_skips_only_that_glob(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "notes/big.py", 5001)
    _write(tmp_path, "src/big.py", 5001)
    assert _check(tmp_path, "notes/big.py", excludes=("notes/**",)) == []
    assert _check(tmp_path, "src/big.py", excludes=("notes/**",))


def test_missing_baseline_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/app.py", 10)
    status = main(
        [
            str(tmp_path / "src/app.py"),
            "--baseline",
            str(tmp_path / "missing.json"),
        ]
    )
    assert status == 1
    assert "not in the tree" in capsys.readouterr().err


def test_invalid_baseline_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/app.py", 10)
    path = _baseline(tmp_path, "[]\n")
    status = main([str(tmp_path / "src/app.py"), "--baseline", str(path)])
    assert status == 1
    assert "JSON object" in capsys.readouterr().err


def test_cli_limit(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path, "{}\n")
    _write(tmp_path, "src/app.py", 11)
    target = str(tmp_path / "src/app.py")
    assert main(["--limit", "10", "--baseline", str(baseline), target]) == 1
    assert main(["--limit", "11", "--baseline", str(baseline), target]) == 0


def test_empty_path_list_exits_zero() -> None:
    assert main([]) == 0


def test_nul_bytes_count_toward_the_limit(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    target = tmp_path / "src" / "wide.txt"
    target.parent.mkdir()
    target.write_bytes(b"\x00" * (5001 * BYTES))
    messages = _check(tmp_path, "src/wide.txt")
    assert "src/wide.txt has 5001 tokens (limit 5000)." in messages[0]


def test_image_with_nul_bytes_stays_excluded(tmp_path: Path) -> None:
    _baseline(tmp_path, "{}\n")
    _write(tmp_path, "assets/logo.png", 5001)
    assert _check(tmp_path, "assets/logo.png") == []


def test_staged_rename_keeps_the_old_baseline(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    old = source / "old.py"
    body = b"line of text\n" * 20
    old.write_bytes(body)
    _baseline(tmp_path, '{"src/old.py": 65}\n')
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "mv", "src/old.py", "src/new.py")
    new = source / "new.py"
    new.write_bytes(body + b"extra\n")
    _git(tmp_path, "add", "-A")
    messages = _check(tmp_path, "src/new.py")
    assert (
        "src/new.py has 67 tokens, above its baseline of 65 (limit 5000)."
        in messages[0]
    )
    new.write_bytes(body)
    _git(tmp_path, "add", "-A")
    assert _check(tmp_path, "src/new.py") == []


def test_forty_percent_rewrite_keeps_the_old_baseline(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    old_lines = [f"alpha line {i:04d} keeps its own words\n" for i in range(100)]
    old_body = "".join(old_lines).encode()
    (source / "old.py").write_bytes(old_body)
    new_lines = [
        f"bravo line {i:04d} replaced with other words\n" if i < 60 else old_lines[i]
        for i in range(100)
    ]
    new_lines.append("extra growth line one\n")
    new_body = "".join(new_lines).encode()
    recorded = token_count(len(old_body))
    grown = token_count(len(new_body))
    assert grown > recorded
    _baseline(tmp_path, f'{{"src/old.py": {recorded}}}\n')
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "mv", "src/old.py", "src/new.py")
    (source / "new.py").write_bytes(new_body)
    _git(tmp_path, "add", "-A")
    messages = _check(tmp_path, "src/new.py")
    assert (
        f"src/new.py has {grown} tokens, above its baseline of {recorded} (limit 5000)."
    ) in messages[0]


def test_rewrite_git_does_not_call_a_rename_is_a_new_file(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    old_lines = [f"alpha line {i:04d} keeps its own words\n" for i in range(100)]
    (source / "old.py").write_bytes("".join(old_lines).encode())
    _baseline(tmp_path, '{"src/old.py": 10}\n')
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "mv", "src/old.py", "src/new.py")
    new_lines = [
        f"totally different content number {i:04d} zzzzz\n" for i in range(120)
    ]
    (source / "new.py").write_bytes("".join(new_lines).encode())
    _git(tmp_path, "add", "-A")
    assert _check(tmp_path, "src/new.py") == []


def _git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=dev", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )
