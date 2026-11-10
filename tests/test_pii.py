import re
from pathlib import Path

from dev_hooks.pii import check_text, main, pesel_ok


def _join(*parts: str) -> str:
    return "".join(parts)


def test_email_outside_the_placeholder_domains_fails() -> None:
    email = "jan.kowalski@gmail.com"
    text = '{"email": "' + email + '"}\n'
    assert check_text(text, relative="tests/fixtures/person.json") == [
        f"tests/fixtures/person.json:1: email {email}"
    ]


def test_example_email_is_ignored() -> None:
    email = _join("person", "@", "example.com")
    text = email + "\n"
    assert check_text(text, relative="tests/fixtures/person.json") == []


def test_valid_pesel_fails_and_an_invalid_number_does_not() -> None:
    valid = _join("440514", "01359")
    invalid = _join("123456", "78901")
    assert pesel_ok(valid)
    assert not pesel_ok(invalid)
    assert check_text(valid + "\n", relative="tests/fixtures/ids.txt") == [
        f"tests/fixtures/ids.txt:1: pesel {valid}"
    ]
    assert check_text(invalid + "\n", relative="tests/fixtures/ids.txt") == []


def test_international_and_labeled_phones_fail() -> None:
    international = _join("+48 ", "600 123 456")
    labeled = _join("phone: ", "600123456")
    bare = _join("600", "123456")
    assert "phone" in check_text(international + "\n", relative="tests/a.txt")[0]
    assert "phone" in check_text(labeled + "\n", relative="tests/a.txt")[0]
    assert check_text(bare + "\n", relative="tests/a.txt") == []


def test_polish_phones_with_parentheses_fail() -> None:
    international = "+48 (600) 123-456"
    local = "tel. (22) 123 45 67"
    assert "phone" in check_text(international + "\n", relative="tests/a.txt")[0]
    assert "phone" in check_text(local + "\n", relative="tests/a.txt")[0]


def test_example_subdomain_is_ignored() -> None:
    email = "person@mail.example.com"
    assert check_text(email + "\n", relative="tests/a.txt") == []


def test_surname_may_start_with_a_polish_capital() -> None:
    first = "Anna Ąkowska\n"
    second = "Ewa Ędzka\n"
    assert check_text(first, relative="tests/a.txt") == [
        "tests/a.txt:1: name Anna Ąkowska"
    ]
    assert check_text(second, relative="tests/a.txt") == [
        "tests/a.txt:1: name Ewa Ędzka"
    ]


def test_repeated_digit_phone_is_a_placeholder() -> None:
    number = _join("+48 ", "000 000 000")
    assert check_text(number + "\n", relative="tests/a.txt") == []


def test_capitalized_pair_is_a_name() -> None:
    text = "Anna Kowalska\n"
    assert check_text(text, relative="tests/person.html") == [
        "tests/person.html:1: name Anna Kowalska"
    ]


def test_lowercase_prose_and_placeholder_surname_are_ignored() -> None:
    prose = "Grace period and Mark the file.\n"
    placeholder = "Jane Doe\n"
    assert check_text(prose, relative="tests/a.txt") == []
    assert check_text(placeholder, relative="tests/a.txt") == []


def test_labeled_first_name_fails_and_an_ordinary_value_does_not() -> None:
    hit = '{"first_name": "Anna"}\n'
    miss = '{"name": "Widget"}\n'
    assert "name Anna" in check_text(hit, relative="tests/person.json")[0]
    assert check_text(miss, relative="tests/person.json") == []


def test_pii_ok_and_allowlist_suppress_a_line() -> None:
    email = _join("jan.kowalski", "@", "gmail.com")
    marked = email + " pii-ok\n"
    assert check_text(marked, relative="tests/a.txt") == []
    allow = [re.compile(re.escape(email))]
    assert check_text(email + "\n", relative="tests/a.txt", allow=allow) == []


def test_path_outside_tests_and_fixtures_is_ignored() -> None:
    email = _join("jan.kowalski", "@", "gmail.com")
    assert check_text(email + "\n", relative="src/app.py") == []


def test_custom_glob_can_include_another_tree() -> None:
    email = _join("jan.kowalski", "@", "gmail.com")
    assert check_text(email + "\n", relative="data/people.json", globs=("data/**",))


def test_fixture_decodes_utf16_bom_and_cp1250(tmp_path: Path) -> None:
    from dev_hooks.pii import check_path

    email = "jan.kowalski@gmail.com"
    utf16 = tmp_path / "tests" / "wide.txt"
    legacy = tmp_path / "tests" / "legacy.txt"
    broken = tmp_path / "tests" / "broken.bin"
    utf16.parent.mkdir(parents=True)
    utf16.write_bytes((email + "\n").encode("utf-16"))
    legacy.write_bytes(email.encode() + b" " + "Łukasz".encode("cp1250"))
    broken.write_bytes(b"\xff\x00\xfe")
    assert any(
        email in item
        for item in check_path(
            utf16, tmp_path, globs=("tests/**",), excludes=(), allow=()
        )
    )
    assert any(
        email in item
        for item in check_path(
            legacy, tmp_path, globs=("tests/**",), excludes=(), allow=()
        )
    )
    assert check_path(broken, tmp_path, globs=("tests/**",), excludes=(), allow=()) == [
        "tests/broken.bin: file cannot be decoded"
    ]


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


_BMP = bytes.fromhex(
    "424d3a00000000000000ff00000028000000010000000100000001001800"
    "00000000040000000000000000000000000000000000000000000000"
)


def test_bmp_fixture_is_skipped(tmp_path: Path) -> None:
    from dev_hooks.pii import check_path

    assert len(_BMP) == 58
    assert _BMP.count(b"\x00") == 48
    pixel = tmp_path / "tests" / "fixtures" / "pixel.bmp"
    pixel.parent.mkdir(parents=True)
    pixel.write_bytes(_BMP)
    assert check_path(pixel, tmp_path, globs=("tests/**",), excludes=(), allow=()) == []
    email = "jan.kowalski@gmail.com"
    text = tmp_path / "tests" / "fixtures" / "label.txt"
    text.write_bytes(b"BM hello\n" + email.encode() + b"\n")
    assert check_path(text, tmp_path, globs=("tests/**",), excludes=(), allow=()) == [
        f"tests/fixtures/label.txt:2: email {email}"
    ]


def test_binary_fixture_is_skipped(tmp_path: Path) -> None:
    from dev_hooks.pii import check_path

    assert len(_PNG) == 67
    assert _PNG.count(b"\x00") == 23
    pixel = tmp_path / "tests" / "fixtures" / "pixel.png"
    pixel.parent.mkdir(parents=True)
    pixel.write_bytes(_PNG)
    assert check_path(pixel, tmp_path, globs=("tests/**",), excludes=(), allow=()) == []
    odd = tmp_path / "tests" / "fixtures" / "odd.bin"
    odd.write_bytes(bytes((0x81, 0x83, 0x88, 0x90, 0x98)))
    assert check_path(odd, tmp_path, globs=("tests/**",), excludes=(), allow=()) == []


def test_utf16_without_a_bom_is_scanned(tmp_path: Path) -> None:
    from dev_hooks.pii import check_path

    email = "jan.kowalski@gmail.com"
    for encoding in ("utf-16-le", "utf-16-be"):
        path = tmp_path / "tests" / f"wide-{encoding}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((email + "\n").encode(encoding))
        assert check_path(
            path, tmp_path, globs=("tests/**",), excludes=(), allow=()
        ) == [f"tests/wide-{encoding}.txt:1: email {email}"]


def test_utf8_nul_beside_an_email_stays_utf8(tmp_path: Path) -> None:
    from dev_hooks.pii import check_path

    email = "jan.kowalski@gmail.com"
    path = tmp_path / "tests" / "beside.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(email.encode() + b"\x00\n")
    assert check_path(path, tmp_path, globs=("tests/**",), excludes=(), allow=()) == [
        f"tests/beside.txt:1: email {email}"
    ]


def test_cli_fails_on_a_fixture_and_passes_outside_it(tmp_path: Path) -> None:
    email = _join("jan.kowalski", "@", "gmail.com")
    fixture = tmp_path / "tests" / "fixtures" / "person.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(email + "\n", encoding="utf-8")
    other = tmp_path / "src" / "app.json"
    other.parent.mkdir()
    other.write_text(email + "\n", encoding="utf-8")
    assert main([str(fixture)]) == 1
    assert main([str(other)]) == 0
