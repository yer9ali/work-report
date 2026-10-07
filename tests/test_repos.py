import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from repos import own_commits, own_merges, recent_authors, repo_root

START = datetime(2026, 10, 7, tzinfo=timezone.utc)
END = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _git(
    repo: Path,
    *args: str,
    when: str = "2026-10-07T10:00:00+00:00",
    author: str = "Me <me@example.com>",
) -> str:
    name, email = author[:-1].split(" <")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, env=env, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "shop_api"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "старт", when="2026-10-01T10:00:00+00:00")
    return repo


def test_only_own_commits_in_the_period_are_taken(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "fix/a")
    _git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "Мой фикс\n\nдетали",
        author="Me <Me@example.com>",
    )
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Чужой", author="Other <o@example.com>")
    _git(
        repo, "commit", "-q", "--allow-empty", "-m", "Мой старый", when="2026-10-05T10:00:00+00:00"
    )

    commits = own_commits(repo, ["me@example.com"], START, END)

    assert [c.subject for c in commits] == ["Мой фикс"]
    assert commits[0].body == "детали"
    assert "fix/a" in commits[0].branches


def test_a_merge_into_dev_with_own_work_is_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feat/x")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Фича")
    _git(repo, "checkout", "-q", "dev")
    _git(
        repo,
        "merge",
        "-q",
        "--no-ff",
        "feat/x",
        "-m",
        "Merge branch 'feat/x' into 'dev'",
        when="2026-10-07T12:00:00+00:00",
        author="GitLab <gl@example.com>",
    )

    [merge] = own_merges(repo, ["me@example.com"], START, END)

    assert (merge.branch, merge.target) == ("feat/x", "dev")


def test_repo_root_resolves_worktrees_and_rejects_non_git(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(worktree), "-b", "wt-branch")

    assert repo_root(str(worktree)) == repo.resolve()
    assert repo_root(str(tmp_path / "missing")) is None
    plain = tmp_path / "plain"
    plain.mkdir()
    assert repo_root(str(plain)) is None


def test_recent_authors_lists_people_by_commit_count(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    for _ in range(2):
        _git(repo, "commit", "-q", "--allow-empty", "-m", "x", when=now)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "y", author="Other <o@example.com>", when=now)

    assert recent_authors(repo, days=14)[0] == "Me <me@example.com>"


def _old_git(monkeypatch, banned: tuple[str, ...]) -> None:
    import repos

    real = repos._git

    def fake(repo: Path, *args: str) -> str | None:
        if any(a.startswith(banned) for a in args):
            return None
        return real(repo, *args)

    monkeypatch.setattr(repos, "_git", fake)


def test_old_git_without_since_as_filter_still_works(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feat/x")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Фича")
    _git(repo, "checkout", "-q", "dev")
    _git(
        repo, "merge", "-q", "--no-ff", "feat/x", "-m", "Merge branch 'feat/x' into 'dev'",
        when="2026-10-07T12:00:00+00:00", author="GitLab <gl@example.com>",
    )  # fmt: skip
    _old_git(monkeypatch, ("--since-as-filter",))

    assert [c.subject for c in own_commits(repo, ["me@example.com"], START, END)] == ["Фича"]
    [merge] = own_merges(repo, ["me@example.com"], START, END)
    assert (merge.branch, merge.target) == ("feat/x", "dev")


def test_old_git_without_path_format_still_resolves_root(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(worktree), "-b", "wt-branch")
    _old_git(monkeypatch, ("--path-format=absolute",))

    assert repo_root(str(worktree)) == repo.resolve()
    assert repo_root(str(repo)) == repo.resolve()
