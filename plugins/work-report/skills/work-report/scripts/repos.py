"""Git: the person's own commits and the merges that landed them."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from period import parse_ts

_TARGETS = ("dev", "main", "origin/dev", "origin/main")
_MERGE_BRANCH = re.compile(r"Merge (?:remote-tracking )?branch '([^']+)'")
_FIELD, _RECORD = "\x1f", "\x1e"


@dataclass
class Commit:
    sha: str
    at: datetime
    subject: str
    body: str
    branches: list[str] = field(default_factory=list)


@dataclass
class Merge:
    sha: str
    at: datetime
    branch: str
    target: str


def _git(repo: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def repo_root(cwd: str) -> Path | None:
    path = Path(cwd)
    if not cwd or not path.is_dir():
        return None
    common = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None:  # git < 2.31: no --path-format, the path may come back relative
        common = _git(path, "rev-parse", "--git-common-dir")
        if common is None:
            return None
        common_dir = (path / common.strip()).resolve()
    else:
        common_dir = Path(common.strip())
    if common_dir.name == ".git":
        return common_dir.parent.resolve()
    top = _git(path, "rev-parse", "--show-toplevel")
    return Path(top.strip()).resolve() if top else None


def _author_args(authors: list[str]) -> list[str]:
    return ["--regexp-ignore-case", "--fixed-strings", *[f"--author={a}" for a in authors]]


def _range(start: datetime, end: datetime) -> list[str]:
    return [f"--since-as-filter={start.isoformat()}", f"--until={end.isoformat()}"]


def _git_ranged(repo: Path, start: datetime, end: datetime, *args: str) -> str | None:
    """Run git with date flags; on git < 2.37 retry without them (callers filter in Python)."""
    out = _git(repo, *args[:1], *_range(start, end), *args[1:])
    return out if out is not None else _git(repo, *args)


def own_commits(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Commit]:
    if not authors:
        return []
    out = _git_ranged(
        repo,
        start,
        end,
        "log",
        "--all",
        "--no-merges",
        *_author_args(authors),
        f"--format=%H{_FIELD}%aI{_FIELD}%s{_FIELD}%b{_RECORD}",
    )
    commits = []
    for chunk in (out or "").split(_RECORD):
        parts = chunk.strip("\n").split(_FIELD)
        if len(parts) != 4:
            continue
        sha, at_raw, subject, body = parts
        at = parse_ts(at_raw)
        if at is None or not (start <= at < end):
            continue
        branches = _git(repo, "branch", "-a", "--contains", sha, "--format=%(refname:short)") or ""
        commits.append(
            Commit(
                sha[:7],
                at,
                subject,
                "\n".join(body.strip().splitlines()[:3]),
                [b for b in branches.split() if b][:3],
            )
        )
    return sorted(commits, key=lambda c: c.at)


def own_merges(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Merge]:
    if not authors:
        return []
    merges: dict[str, Merge] = {}
    for target in _TARGETS:
        out = _git_ranged(
            repo,
            start,
            end,
            "log",
            target,
            "--first-parent",
            "--merges",
            f"--format=%H{_FIELD}%aI{_FIELD}%s",
        )
        for line in (out or "").splitlines():
            parts = line.split(_FIELD)
            if len(parts) != 3 or parts[0] in merges:
                continue
            sha, at_raw, subject = parts
            at = parse_ts(at_raw)
            if at is None or not (start <= at < end):
                continue
            mine = _git(repo, "log", "--format=%H", *_author_args(authors), f"{sha}^1..{sha}^2")
            if not mine or not mine.strip():
                continue
            found = _MERGE_BRANCH.search(subject)
            merges[sha] = Merge(
                sha[:7], at, found.group(1) if found else subject, target.removeprefix("origin/")
            )
    return sorted(merges.values(), key=lambda m: m.at)


def recent_authors(repo: Path, days: int) -> list[str]:
    out = _git(repo, "log", "--all", f"--since={days}.days", "--format=%an <%ae>")
    return [author for author, _ in Counter((out or "").splitlines()).most_common() if author]
