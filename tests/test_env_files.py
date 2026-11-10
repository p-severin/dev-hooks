from dev_hooks.env_files import check_relative, finding, main


def test_secret_files_are_blocked() -> None:
    blocked = (
        ".env",
        ".env.local",
        "app/.env.production",
        "run.env",
        "deploy/run.env",
        "secrets/key.txt",
        "src/secrets/api.json",
        ".claude/settings.local.json",
        "pkg/.claude/settings.local.json",
    )
    for relative in blocked:
        assert check_relative(relative) is not None


def test_case_and_secret_directory_segments() -> None:
    blocked = (
        ".ENV",
        "app/.ENV.local",
        "SRC/SECRETS/a.txt",
        "pkg/.env/keys",
        "deploy/Run.env/file",
        ".env/.env.example",
    )
    for relative in blocked:
        assert check_relative(relative) is not None, relative
    assert check_relative(".ENV.EXAMPLE") is None
    assert check_relative("App/.Env.Sample") is None


def test_examples_and_ordinary_files_are_allowed() -> None:
    allowed = (
        ".env.example",
        "app/.env.sample",
        ".env.sample",
        "src/settings.py",
        "notsecrets/key.txt",
        ".claude/settings.json",
        "secrets",
    )
    for relative in allowed:
        assert check_relative(relative) is None


def test_extra_allow_and_deny_globs() -> None:
    assert check_relative(".env.template", allow=("**/.env.template",)) is None
    assert check_relative("notes/local.key", deny=("**/*.key",)) == "denied path"


def test_message_names_the_path() -> None:
    assert finding(".env", "env file") == ".env: do not commit this file (env file)"


def test_cli_exit_codes() -> None:
    assert main([".env"]) == 1
    assert main([".env.example"]) == 0
    assert main([]) == 0
    assert main(["--allow", "**/.env.local", ".env.local"]) == 0
