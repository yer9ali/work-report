import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "plugins/work-report/skills/work-report/scripts/digest.py"


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-10-07T10:00:00+05:00",
        "GIT_COMMITTER_DATE": "2026-10-07T10:00:00+05:00",
        "GIT_AUTHOR_NAME": "Me",
        "GIT_AUTHOR_EMAIL": "me@example.com",
        "GIT_COMMITTER_NAME": "Me",
        "GIT_COMMITTER_EMAIL": "me@example.com",
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def _setup(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "shop_api"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/dev")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Полный цикл заказа, password=hunter2")
    claude = tmp_path / ".claude"
    folder = claude / "projects" / "p"
    folder.mkdir(parents=True)
    record = {
        "type": "user",
        "timestamp": "2026-10-07T05:00:00Z",
        "sessionId": "s1",
        "cwd": str(repo),
        "gitBranch": "dev",
        "isSidechain": False,
        "message": {"role": "user", "content": "давай пройдём цикл"},
    }
    (folder / "s1.jsonl").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"authors": ["me@example.com"], "reports_dir": str(tmp_path)}), encoding="utf-8"
    )
    products = tmp_path / "products.json"
    products.write_text(json.dumps({"shop_api": "Магазин"}), encoding="utf-8")
    return {"repo": repo, "claude": claude, "config": config, "products": products}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_digest_without_claude_mem_is_complete_and_masked(tmp_path: Path) -> None:
    p = _setup(tmp_path)

    done = _run(
        "--from", "2026-10-07", "--to", "2026-10-07", "--config", str(p["config"]),
        "--claude-dir", str(p["claude"]), "--mem-db", str(tmp_path / "none.db"),
        "--products", str(p["products"]), "--tz", "Asia/Almaty",
    )  # fmt: skip

    assert done.returncode == 0, done.stderr
    assert "источники: git, сессии\n" in done.stdout
    assert "## Магазин (shop_api)" in done.stdout
    assert "Полный цикл заказа" in done.stdout
    assert "давай пройдём цикл" in done.stdout
    assert "hunter2" not in done.stdout


def test_without_config_own_commits_come_from_repo_user_email(tmp_path: Path) -> None:
    p = _setup(tmp_path)
    _git(p["repo"], "config", "user.email", "ME@example.com")
    p["config"].unlink()

    done = _base(p, tmp_path)

    assert done.returncode == 0, done.stderr
    assert "Полный цикл заказа" in done.stdout


def test_suggest_authors_lists_committers_of_session_repos(tmp_path: Path) -> None:
    p = _setup(tmp_path)

    done = _run("--suggest-authors", "--claude-dir", str(p["claude"]), "--days", "100000")

    assert done.returncode == 0, done.stderr
    assert "Me <me@example.com>" in json.loads(done.stdout)


def _base(p: dict[str, Path], tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return _run(
        "--from", "2026-10-07", "--to", "2026-10-07", "--config", str(p["config"]),
        "--claude-dir", str(p["claude"]), "--mem-db", str(tmp_path / "none.db"),
        "--products", str(p["products"]), "--tz", "Asia/Almaty", *extra,
    )  # fmt: skip


def test_broken_config_exits_3_and_bad_authors_are_ignored(tmp_path: Path) -> None:
    p = _setup(tmp_path)
    for bad in ("[]", "{not json"):
        p["config"].write_text(bad, encoding="utf-8")
        done = _base(p, tmp_path)
        assert done.returncode == 3, bad
        assert "JSON-объект" in done.stderr
    p["config"].write_text('{"authors": "me@example.com"}', encoding="utf-8")
    done = _base(p, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "authors" in done.stderr


def test_bad_extra_repos_is_ignored_with_a_warning(tmp_path: Path) -> None:
    p = _setup(tmp_path)
    p["config"].write_text(
        json.dumps({"authors": ["me@example.com"], "extra_repos": "x"}), encoding="utf-8"
    )
    done = _base(p, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "extra_repos" in done.stderr


def test_reversed_dates_and_bad_tz_exit_2(tmp_path: Path) -> None:
    p = _setup(tmp_path)
    done = _run("--from", "2026-10-08", "--to", "2026-10-07", "--config", str(p["config"]))
    assert done.returncode == 2 and done.stderr
    done = _base(p, tmp_path, "--tz", "No/Such")
    assert done.returncode == 2 and done.stderr


def test_sessions_in_excluded_paths_are_skipped(tmp_path: Path) -> None:
    p = _setup(tmp_path)
    obs = tmp_path / "observer"
    obs.mkdir()
    folder = p["claude"] / "projects" / "o"
    folder.mkdir()
    record = {
        "type": "user", "timestamp": "2026-10-07T05:00:00Z", "sessionId": "o1",
        "cwd": str(obs), "isSidechain": False,
        "message": {"role": "user", "content": "служебная сессия"},
    }  # fmt: skip
    (folder / "o1.jsonl").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    p["config"].write_text(
        json.dumps({"authors": ["me@example.com"], "exclude_paths": [str(obs)]}), encoding="utf-8"
    )
    done = _base(p, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "служебная сессия" not in done.stdout
    assert "давай пройдём цикл" in done.stdout


def test_check_update_reads_own_version_and_stays_quiet_offline() -> None:
    import digest

    assert digest._version(digest.PLUGIN_JSON.read_text(encoding="utf-8")) >= (0, 3, 2)
    digest.LATEST_URL = "http://127.0.0.1:9/plugin.json"  # nothing listens: offline
    assert digest._check_update() == 0
