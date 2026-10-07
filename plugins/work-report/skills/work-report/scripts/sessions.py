"""Claude Code sessions: what the person asked and what each turn ended with."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from period import parse_ts

_USER_LIMIT = 500
_ANSWER_LIMIT = 800
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_PASTE = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
_BASH_INPUT = re.compile(r"<bash-input>(.*?)</bash-input>", re.S)
_SERVICE_TAGS = re.compile(
    r"<(bash-stdout|bash-stderr|local-command-caveat|local-command-stdout"
    r"|command-name|command-message|command-args)>.*?</\1>",
    re.S,
)
_SKIP_PREFIXES = ("Base directory for this skill", "[Request interrupted by user")


@dataclass
class Turn:
    role: str
    text: str
    at: datetime


@dataclass
class Session:
    session_id: str
    cwd: str
    title: str | None
    branches: list[str]
    start: datetime
    end: datetime
    turns: list[Turn] = field(default_factory=list)


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _bash_line(match: re.Match[str]) -> str:
    lines = match.group(1).strip().splitlines()
    return f"! {lines[0]}" if lines else ""


def _clean_user_text(content: object) -> str | None:
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    text = _REMINDER.sub("", content)
    text = _PASTE.sub(lambda m: f"[вставка {len(m.group(1))} симв.]", text)
    text = _BASH_INPUT.sub(_bash_line, text)
    text = _SERVICE_TAGS.sub("", text).strip()
    if not text or text.startswith(_SKIP_PREFIXES):
        return None
    return _shorten(text, _USER_LIMIT)


def _assistant_text(content: object) -> str | None:
    if not isinstance(content, list):
        return None
    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    texts = [t for t in texts if t.strip()]
    return _shorten(texts[-1], _ANSWER_LIMIT) if texts else None


def _read(path: Path, start: datetime, end: datetime) -> Session | None:
    title: str | None = None
    session: Session | None = None
    pending: Turn | None = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("type") == "ai-title" and record.get("aiTitle"):
            title = str(record["aiTitle"])
            continue
        if record.get("type") not in {"user", "assistant"} or record.get("isSidechain"):
            continue
        at = parse_ts(record.get("timestamp"))
        if at is None or not (start <= at < end):
            continue
        content = (record.get("message") or {}).get("content")
        if record["type"] == "user":
            if record.get("isMeta"):
                continue
            text = _clean_user_text(content)
            if text is None:
                continue
            turn = Turn("user", text, at)
        else:
            text = _assistant_text(content)
            if text is None:
                continue
            pending = Turn("assistant", text, at)
            turn = None
        if session is None:
            session = Session(
                str(record.get("sessionId", path.stem)),
                str(record.get("cwd", "")),
                None,
                [],
                at,
                at,
            )
        session.end = max(session.end, at)
        branch = record.get("gitBranch")
        if branch and branch not in session.branches:
            session.branches.append(str(branch))
        if turn is not None:
            if pending is not None:
                session.turns.append(pending)
                pending = None
            session.turns.append(turn)
    if session is None:
        return None
    if pending is not None:
        session.turns.append(pending)
    session.title = title
    return session


def collect_sessions(claude_dir: Path, start: datetime, end: datetime) -> list[Session]:
    projects = claude_dir / "projects"
    if not projects.is_dir():
        return []
    found = []
    for path in sorted(projects.glob("*/*.jsonl")):
        try:
            if path.stat().st_mtime < start.timestamp():
                continue
        except OSError:
            continue
        session = _read(path, start, end)
        if session is not None:
            found.append(session)
    return sorted(found, key=lambda s: s.start)
