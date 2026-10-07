"""claude-mem session summaries — optional: absent or unreadable means "no such source"."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from period import parse_ts


@dataclass
class MemSummary:
    project: str
    completed: str
    next_steps: str
    at: datetime


def read_summaries(db: Path, start: datetime, end: datetime) -> list[MemSummary] | None:
    if not db.is_file():
        return None
    since = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    until = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            rows = con.execute(
                "select project, coalesce(completed,''), coalesce(next_steps,''), created_at"
                " from session_summaries where created_at >= ? and created_at < ?"
                " order by created_at",
                (since, until),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    found = []
    for project, completed, next_steps, created in rows:
        at = parse_ts(created)
        if at is None or not (completed.strip() or next_steps.strip()):
            continue
        found.append(
            MemSummary(str(project).split("/")[0], completed.strip(), next_steps.strip(), at)
        )
    return found
