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
