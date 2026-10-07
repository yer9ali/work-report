"""The digest as Markdown, grouped by product, cut to a line limit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, tzinfo

from mem import MemSummary
from repos import Commit, Merge
from sessions import Session, Turn

# (max chars per text, max turns kept per session or None, max claude-mem summaries kept per
# project or None) — tried in order until the digest fits. claude-mem is the most expendable
# source (up to ~100 summaries a day), so it shrinks first and is dropped before session
# titles and outcomes are touched.
_STEPS = (
    (800, None, None),
    (300, None, None),
    (150, None, 20),
    (150, 8, 5),
    (150, 2, 0),
    (80, 2, 0),
)


@dataclass
class Activity:
    repo_name: str
    product: str
    commits: list[Commit] = field(default_factory=list)
    merges: list[Merge] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    mem: list[MemSummary] = field(default_factory=list)

    @property
    def weight(self) -> int:
        return len(self.commits) + len(self.sessions)


def _cut(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


def _turns(turns: list[Turn], keep: int | None) -> list[Turn]:
    if keep is None or len(turns) <= keep:
        return turns
    return [turns[0], *turns[len(turns) - (keep - 1) :]] if keep > 1 else turns[-1:]


def _lines(
    activities: list[Activity],
    start: date,
    end: date,
    sources: list[str],
    tz: tzinfo,
    chars: int,
    keep: int | None,
    mem_keep: int | None,
) -> list[str]:
    def stamp(at):  # noqa: ANN001, ANN202
        return at.astimezone(tz).strftime("%m-%d %H:%M")

    out = [f"# Выжимка {start.isoformat()} — {end.isoformat()}", f"источники: {', '.join(sources)}"]
    for act in sorted(activities, key=lambda a: -a.weight):
        title = act.product if act.product == act.repo_name else f"{act.product} ({act.repo_name})"
        out += ["", f"## {title}"]
        if act.commits or act.merges:
            out.append("### Коммиты")
            out += [
                f"- {c.sha} {stamp(c.at)} [{', '.join(c.branches) or '—'}] {c.subject}"
                + (f" — {_cut(c.body, 200)}" if c.body else "")
                for c in act.commits
            ]
            out += [f"- влито {m.branch} → {m.target} {stamp(m.at)}" for m in act.merges]
        if act.sessions:
            out.append("### Сессии")
            for s in act.sessions:
                title = f"«{s.title}»" if s.title else "«без названия»"
                span = f"{s.start.astimezone(tz):%H:%M}–{s.end.astimezone(tz):%H:%M}"
                out.append(f"- {span} {title} [{', '.join(s.branches) or '—'}]")
                for t in _turns(s.turns, keep):
                    who = "пользователь" if t.role == "user" else "итог"
                    out.append(f"  - {who}: {_cut(t.text, chars)}")
        mem = (
            act.mem if mem_keep is None else act.mem[len(act.mem) - mem_keep :] if mem_keep else []
        )
        if mem:
            out.append("### claude-mem")
            for m in mem:
                if m.completed:
                    out.append(f"- сделано: {_cut(m.completed, chars)}")
                if m.next_steps:
                    out.append(f"- дальше: {_cut(m.next_steps, chars)}")
    return out


def render(
    activities: list[Activity],
    start: date,
    end: date,
    sources: list[str],
    tz: tzinfo,
    limit: int = 2000,
) -> str:
    lines: list[str] = []
    for chars, keep, mem_keep in _STEPS:
        lines = _lines(activities, start, end, sources, tz, chars, keep, mem_keep)
        if len(lines) <= limit:
            break
    if len(lines) > limit:
        lines = lines[: limit - 1] + ["… (выжимка обрезана по лимиту)"]
    return "\n".join(lines) + "\n"
