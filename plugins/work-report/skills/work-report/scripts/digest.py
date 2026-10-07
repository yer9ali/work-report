#!/usr/bin/env python3
"""Digest of one person's work for a period: git + Claude Code sessions (+ claude-mem).

digest.py --from 2026-10-07 --to 2026-10-07
digest.py --suggest-authors
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mask import mask_secrets
from mem import read_summaries
from period import period_bounds
from products import load_products, product_for
from render import Activity, render
from repos import own_commits, own_merges, recent_authors, repo_root
from sessions import collect_sessions

HERE = Path(__file__).resolve().parent
DEFAULT_REPORTS = Path("~/work-reports").expanduser()
EXIT_NO_CONFIG = 3
DEFAULT_EXCLUDES = ("~/.claude-mem",)


def _args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from", dest="start", type=date.fromisoformat)
    p.add_argument("--to", dest="end", type=date.fromisoformat)
    p.add_argument("--config", type=Path, default=DEFAULT_REPORTS / "config.json")
    p.add_argument("--claude-dir", type=Path, default=Path("~/.claude").expanduser())
    p.add_argument("--mem-db", type=Path, default=Path("~/.claude-mem/claude-mem.db").expanduser())
    p.add_argument("--products", type=Path, default=HERE.parent / "reference" / "products.json")
    p.add_argument("--tz", help="IANA zone; default — local zone of the machine")
    p.add_argument("--suggest-authors", action="store_true")
    p.add_argument("--days", type=int, default=14)
    return p.parse_args(argv)


def _resolved(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _str_list(config: dict, key: str) -> list[str]:
    value = config.get(key, [])
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    print(f"конфиг: {key} должен быть списком строк — игнорирую", file=sys.stderr)
    return []


def _suggest(args: argparse.Namespace) -> int:
    now = datetime.now().astimezone()
    sessions = collect_sessions(args.claude_dir, now - timedelta(days=args.days), now)
    roots = {r for r in (repo_root(s.cwd) for s in sessions) if r}
    counts: dict[str, int] = {}
    for root in roots:
        for rank, author in enumerate(recent_authors(root, args.days)):
            counts[author] = counts.get(author, 0) + 100 - rank
    print(json.dumps(sorted(counts, key=lambda a: -counts[a]), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str]) -> int:
    args = _args(argv)
    if args.suggest_authors:
        return _suggest(args)
    if args.start is None or args.end is None:
        print("нужны --from и --to (YYYY-MM-DD)", file=sys.stderr)
        return 2
    if args.start > args.end:
        print("--from позже --to", file=sys.stderr)
        return 2
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            f"нет конфига {args.config}: сначала digest.py --suggest-authors и создать "
            "config.json с полем authors",
            file=sys.stderr,
        )
        return EXIT_NO_CONFIG
    authors = config.get("authors") if isinstance(config, dict) else None
    if not (isinstance(authors, list) and authors and all(isinstance(a, str) for a in authors)):
        print(
            f"конфиг {args.config}: нужен объект с непустым списком строк authors "
            '(например {"authors": ["me@example.com"]})',
            file=sys.stderr,
        )
        return EXIT_NO_CONFIG
    reports_dir = Path(config.get("reports_dir", DEFAULT_REPORTS)).expanduser()
    extra_repos = _str_list(config, "extra_repos")
    excludes = [_resolved(p) for p in (*DEFAULT_EXCLUDES, *_str_list(config, "exclude_paths"))]
    try:
        tz = ZoneInfo(args.tz) if args.tz else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        print(f"неизвестная зона --tz {args.tz}", file=sys.stderr)
        return 2
    start, end = period_bounds(args.start, args.end, tz)

    mapping = load_products(args.products, reports_dir / "products.json")
    sessions = [
        s
        for s in collect_sessions(args.claude_dir, start, end)
        if not any(_resolved(s.cwd).is_relative_to(x) for x in excludes)
    ]
    by_name: dict[str, Activity] = {}
    roots: dict[str, Path | None] = {}
    for s in sessions:
        root = repo_root(s.cwd)
        name = root.name if root else (Path(s.cwd).name or "без проекта")
        roots.setdefault(name, root)
        by_name.setdefault(name, Activity(name, product_for(name, mapping))).sessions.append(s)
    for extra in extra_repos:
        root = repo_root(str(Path(extra).expanduser()))
        if root:
            roots.setdefault(root.name, root)
    for name, root in roots.items():
        if root is None:
            continue
        commits = own_commits(root, authors, start, end)
        merges = own_merges(root, authors, start, end)
        if commits or merges or name in by_name:
            act = by_name.setdefault(name, Activity(name, product_for(name, mapping)))
            act.commits, act.merges = commits, merges

    sources = ["git", "сессии"]
    summaries = read_summaries(args.mem_db, start, end)
    if summaries is not None:
        sources.append("claude-mem")
        for summary in summaries:
            if summary.project in by_name:
                by_name[summary.project].mem.append(summary)

    activities = [a for a in by_name.values() if a.commits or a.merges or a.sessions]
    print(mask_secrets(render(activities, args.start, args.end, sources, tz)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
