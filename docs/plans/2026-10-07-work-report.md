# work-report — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** плагин Claude Code, который по git и истории сессий пишет карточки выполненных задач за день и недельный отчёт по регламенту.

**Architecture:** скрипт `digest.py` (stdlib Python) собирает компактную выжимку за период из
сессий Claude Code (`~/.claude/projects/*/*.jsonl`), git-репозиториев этих сессий и, если есть,
claude-mem; скилл `SKILL.md` по выжимке пишет карточки/отчёт и ведёт журнал в
`~/work-reports/`. Скрипт разбит на модули по источникам; `digest.py` — только сборка и CLI.

**Tech Stack:** Python 3.10+ (только стандартная библиотека), pytest, ruff, Claude Code plugin/marketplace.

**Spec:** `docs/specs/2026-10-07-work-report-design.md`

## Global Constraints

- Python ≥ 3.10, **только стандартная библиотека** в `scripts/` (pytest и ruff — только для разработки).
- Все источники — **только чтение**; claude-mem открывается `sqlite3` с `mode=ro`.
- **claude-mem необязателен**: его отсутствие или любая ошибка → источник молча пропускается, выжимка полноценна.
- Сообщения коммитов — по-русски, **без** `Co-Authored-By` и любой AI-атрибуции.
- Скрипты: `plugins/work-report/skills/work-report/scripts/`; в SKILL.md путь через `${CLAUDE_PLUGIN_ROOT}/skills/work-report/scripts/digest.py`.
- Вывод выжимки целиком проходит через `mask_secrets` перед печатью.
- Лимит выжимки — 2000 строк; заголовок и итог каждой сессии сохраняются всегда.
- Без push: репозиторий на GitLab создаёт пользователь, push — по его команде.

## Review Focus

- Битая строка JSONL или запись без `timestamp` (`ai-title`) — строка пропускается, заголовок всё равно прикрепляется к сессии. Тест — Task 2.
- Сессия через полночь: попадают только записи внутри периода по местному времени. Тест — Task 2.
- `cwd` сессии удалён или не git — проект без репозитория, без падения. Тест — Task 3.
- Email автора в другом регистре (`Me.Name@…`) — коммит всё равно свой. Тест — Task 3.
- Огромная выжимка — обрезается до лимита, заголовки и итоги сессий на месте. Тест — Task 5.

---

### Task 1: Каркас репозитория и маскировка секретов

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/work-report/.claude-plugin/plugin.json`
- Create: `plugins/work-report/skills/work-report/scripts/mask.py`
- Create: `pyproject.toml`, `.gitignore`
- Test: `tests/test_mask.py`

**Interfaces:**
- Produces: `mask.mask_secrets(text: str) -> str`.

- [ ] **Step 1: Каркас** — создать файлы:

`.claude-plugin/marketplace.json`:
```json
{
  "name": "work-report",
  "owner": { "name": "yer9ali" },
  "plugins": [
    {
      "name": "work-report",
      "source": "./plugins/work-report",
      "description": "Карточки выполненных задач за день и недельный отчёт по регламенту"
    }
  ]
}
```

`plugins/work-report/.claude-plugin/plugin.json`:
```json
{
  "name": "work-report",
  "displayName": "Work Report",
  "version": "0.1.0",
  "description": "Карточки выполненных задач за день и недельный отчёт по регламенту из git и истории сессий Claude Code"
}
```

`pyproject.toml`:
```toml
[project]
name = "work-report"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
pythonpath = ["plugins/work-report/skills/work-report/scripts"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
.ruff_cache/
.venv/
```

- [ ] **Step 2: Тест маскировки** — `tests/test_mask.py`:
```python
from mask import mask_secrets


def test_password_elements_are_masked_whatever_the_prefix() -> None:
    text = "<sender><password>Pa55word!</password></sender><ns:password a='1'>x\ny</ns:password>"

    assert mask_secrets(text) == (
        "<sender><password>***</password></sender><ns:password a='1'>***</ns:password>"
    )


def test_key_value_secrets_are_masked() -> None:
    text = (
        'X-Internal-Token: FAKEtok3nVALUE/xyz\n'
        "password=hunter2&user=a\n"
        '{"token": "abc.def", "secret":"s3"}\n'
        "Authorization: Bearer eyJhbGciOi.payload"
    )

    masked = mask_secrets(text)

    for secret in ("FAKEtok3nVALUE", "hunter2", "abc.def", "s3", "eyJhbGciOi"):
        assert secret not in masked
    assert "user=a" in masked


def test_long_base64_is_replaced_by_its_size() -> None:
    blob = "A" * 400

    assert mask_secrets(f"<data>{blob}</data>") == "<data>[base64 300 байт]</data>"


def test_ordinary_text_is_untouched() -> None:
    text = "Заказ оформлен, номер 100200300400, max tokens left"

    assert mask_secrets(text) == text
```

- [ ] **Step 3: Запустить** — `python3 -m pytest tests/test_mask.py -q` → FAIL `ModuleNotFoundError: mask`.

- [ ] **Step 4: Реализация** — `scripts/mask.py`:
```python
"""Secrets never leave the digest: passwords, tokens and long base64 blobs are masked."""

from __future__ import annotations

import re

_PASSWORD_ELEMENT = re.compile(
    r"(<((?:[\w.-]+:)?password)(?:\s[^>]*)?>)(.*?)(</\2\s*>)", re.S | re.I
)
_KEY_VALUE = re.compile(
    r"""(?ix)
    (?<![\w-])
    ("?(?:x-internal-token|authorization|password|passwd|secret|token|api[_-]?key)"?\s*[:=]\s*)
    ("[^"]*"|'[^']*'|(?:(?:bearer|basic)\s+)?[^\s,;&}]+)
    """
)
_LONG_BASE64 = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def _mask_value(match: re.Match[str]) -> str:
    value = match.group(2)
    if value[:1] in {'"', "'"}:
        return f"{match.group(1)}{value[0]}***{value[0]}"
    return f"{match.group(1)}***"


def mask_secrets(text: str) -> str:
    text = _PASSWORD_ELEMENT.sub(r"\1***\4", text)
    text = _KEY_VALUE.sub(_mask_value, text)
    return _LONG_BASE64.sub(lambda m: f"[base64 {len(m.group(0)) * 3 // 4} байт]", text)
```

- [ ] **Step 5: Запустить** — `python3 -m pytest tests/test_mask.py -q` → PASS; `ruff check . && ruff format --check .` (если ruff не установлен: `python3 -m pip install --user ruff pytest`).

- [ ] **Step 6: Commit**
```bash
git add .claude-plugin plugins pyproject.toml .gitignore tests/test_mask.py
git commit -m "Каркас плагина work-report и маскировка секретов"
```

---

### Task 2: Период и разбор сессий Claude Code

**Files:**
- Create: `plugins/work-report/skills/work-report/scripts/period.py`
- Create: `plugins/work-report/skills/work-report/scripts/sessions.py`
- Test: `tests/test_period.py`, `tests/test_sessions.py`

**Interfaces:**
- Produces:
  - `period.period_bounds(start: date, end: date, tz: tzinfo) -> tuple[datetime, datetime]` — `[начало start, начало end+1)`, aware;
  - `period.parse_ts(value: object) -> datetime | None` — ISO с `Z` → aware UTC; мусор → `None`;
  - `period.week_bounds(today: date) -> tuple[date, date]` — пн–пт недели (в сб/вс — только что закончившейся);
  - `sessions.Turn(role: str, text: str, at: datetime)` (role ∈ `"user"`, `"assistant"`);
  - `sessions.Session(session_id: str, cwd: str, title: str | None, branches: list[str], start: datetime, end: datetime, turns: list[Turn])`;
  - `sessions.collect_sessions(claude_dir: Path, start: datetime, end: datetime) -> list[Session]`.

- [ ] **Step 1: Тесты периода** — `tests/test_period.py`:
```python
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from period import parse_ts, period_bounds, week_bounds

ALMATY = ZoneInfo("Asia/Almaty")


def test_period_covers_whole_local_days() -> None:
    start, end = period_bounds(date(2026, 10, 7), date(2026, 10, 7), ALMATY)

    assert start == datetime(2026, 10, 7, 0, 0, tzinfo=ALMATY)
    assert end == datetime(2026, 10, 8, 0, 0, tzinfo=ALMATY)


def test_parse_ts_reads_z_and_rejects_garbage() -> None:
    assert parse_ts("2026-10-06T12:44:19.414079Z") == datetime(
        2026, 10, 6, 12, 44, 19, 414079, tzinfo=timezone.utc
    )
    assert parse_ts(None) is None
    assert parse_ts("вчера") is None


def test_week_is_monday_to_friday_and_weekend_means_the_week_just_ended() -> None:
    assert week_bounds(date(2026, 10, 7)) == (date(2026, 10, 5), date(2026, 10, 9))
    assert week_bounds(date(2026, 10, 10)) == (date(2026, 10, 5), date(2026, 10, 9))
    assert week_bounds(date(2026, 10, 12)) == (date(2026, 10, 12), date(2026, 10, 16))
```

- [ ] **Step 2: Тесты сессий** — `tests/test_sessions.py`:
```python
import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from period import period_bounds
from sessions import collect_sessions

ALMATY = ZoneInfo("Asia/Almaty")


def _write(claude_dir: Path, project: str, session: str, records: list[object]) -> None:
    folder = claude_dir / "projects" / project
    folder.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in records]
    (folder / f"{session}.jsonl").write_text("\n".join(lines), encoding="utf-8")


def _user(ts: str, text: object, **extra: object) -> dict:
    return {"type": "user", "timestamp": ts, "sessionId": "s1", "cwd": "/repo/a",
            "gitBranch": "dev", "isSidechain": False,
            "message": {"role": "user", "content": text}, **extra}


def _assistant(ts: str, text: str, **extra: object) -> dict:
    return {"type": "assistant", "timestamp": ts, "sessionId": "s1", "cwd": "/repo/a",
            "gitBranch": "dev", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "thinking", "thinking": "x"},
                                    {"type": "text", "text": text}]}, **extra}


def _day(d: date):
    return period_bounds(d, d, ALMATY)


def test_a_session_keeps_real_user_text_and_the_last_answer_of_each_turn(tmp_path: Path) -> None:
    _write(tmp_path, "p", "s1", [
        _user("2026-10-07T04:00:00Z", "давай пройдём цикл"),
        _assistant("2026-10-07T04:00:05Z", "промежуточный ответ"),
        _user("2026-10-07T04:00:06Z", [{"type": "tool_result", "content": "лог"}]),
        _assistant("2026-10-07T04:00:09Z", "Цикл прошёл"),
        _user("2026-10-07T04:01:00Z", "Base directory for this skill: /x", isMeta=True),
        {"type": "ai-title", "aiTitle": "Проверка цикла заказа", "sessionId": "s1"},
        "{битая строка",
    ])

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert session.title == "Проверка цикла заказа"
    assert session.cwd == "/repo/a"
    assert session.branches == ["dev"]
    assert [(t.role, t.text) for t in session.turns] == [
        ("user", "давай пройдём цикл"),
        ("assistant", "Цикл прошёл"),
    ]


def test_only_records_inside_the_local_day_are_taken(tmp_path: Path) -> None:
    _write(tmp_path, "p", "s1", [
        _user("2026-10-06T18:30:00Z", "вчера 23:30 по Алматы"),
        _assistant("2026-10-06T18:31:00Z", "вчерашний ответ"),
        _user("2026-10-06T19:30:00Z", "сегодня 00:30 по Алматы"),
        _assistant("2026-10-06T19:31:00Z", "сегодняшний ответ"),
    ])

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert [t.text for t in session.turns] == ["сегодня 00:30 по Алматы", "сегодняшний ответ"]


def test_subagents_and_service_tags_are_left_out(tmp_path: Path) -> None:
    long_paste = "<pasted_content id=\"x\">" + "z" * 5000 + "</pasted_content id=\"x\">"
    _write(tmp_path, "p", "s1", [
        _user("2026-10-07T04:00:00Z",
              "<system-reminder>шум</system-reminder>смотри " + long_paste),
        _user("2026-10-07T04:00:01Z", "<bash-input>git status</bash-input>"),
        _assistant("2026-10-07T04:00:02Z", "ответ субагента", isSidechain=True),
    ])

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    texts = [t.text for t in session.turns]
    assert texts[0].startswith("смотри [вставка")
    assert "шум" not in texts[0]
    assert texts[1] == "! git status"
    assert all("субагента" not in t for t in texts)


def test_a_session_outside_the_period_is_not_returned(tmp_path: Path) -> None:
    _write(tmp_path, "p", "s1", [_user("2026-10-01T04:00:00Z", "давно")])

    assert collect_sessions(tmp_path, *_day(date(2026, 10, 7))) == []
```

- [ ] **Step 3: Запустить** — `python3 -m pytest tests/test_period.py tests/test_sessions.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Реализация** — `scripts/period.py`:
```python
"""Report periods in local time, and timestamps from session files."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo


def period_bounds(start: date, end: date, tz: tzinfo) -> tuple[datetime, datetime]:
    """`[start 00:00, end+1 00:00)` in `tz` — whole local days, end inclusive."""
    return datetime.combine(start, time.min, tz), datetime.combine(end + timedelta(days=1), time.min, tz)


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def week_bounds(today: date) -> tuple[date, date]:
    """Monday–Friday of this week; on a weekend, of the week that just ended."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=4)
```

`scripts/sessions.py`:
```python
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
_BASH_OUTPUT = re.compile(r"<bash-(?:stdout|stderr)>.*?</bash-(?:stdout|stderr)>", re.S)
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
    text = _BASH_INPUT.sub(lambda m: "! " + m.group(1).strip().splitlines()[0], text)
    text = _BASH_OUTPUT.sub("", text).strip()
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
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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
            session = Session(str(record.get("sessionId", path.stem)), str(record.get("cwd", "")),
                              None, [], at, at)
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
        if path.stat().st_mtime < start.timestamp():
            continue
        session = _read(path, start, end)
        if session is not None:
            found.append(session)
    return sorted(found, key=lambda s: s.start)
```

- [ ] **Step 5: Запустить** — `python3 -m pytest tests/test_period.py tests/test_sessions.py -q` → PASS. Тестовые файлы пишутся «сейчас», поэтому фильтр по mtime их пропускает.

- [ ] **Step 6: Commit**
```bash
git add plugins/work-report/skills/work-report/scripts/period.py plugins/work-report/skills/work-report/scripts/sessions.py tests/test_period.py tests/test_sessions.py
git commit -m "Выжимка: период по местному времени и разбор сессий Claude Code"
```

---

### Task 3: Git — свои коммиты и merge

**Files:**
- Create: `plugins/work-report/skills/work-report/scripts/repos.py`
- Test: `tests/test_repos.py`

**Interfaces:**
- Produces:
  - `repos.repo_root(cwd: str) -> Path | None` — корень основного репозитория (worktree → основной), не git/нет каталога → `None`;
  - `repos.Commit(sha: str, at: datetime, subject: str, body: str, branches: list[str])`;
  - `repos.Merge(sha: str, at: datetime, branch: str, target: str)`;
  - `repos.own_commits(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Commit]`;
  - `repos.own_merges(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Merge]`;
  - `repos.recent_authors(repo: Path, days: int) -> list[str]` — `"Имя <email>"`, по убыванию числа коммитов.

- [ ] **Step 1: Тест** — `tests/test_repos.py`:
```python
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from repos import own_commits, own_merges, recent_authors, repo_root

START = datetime(2026, 10, 7, tzinfo=timezone.utc)
END = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _git(repo: Path, *args: str, when: str = "2026-10-07T10:00:00+00:00",
         author: str = "Me <me@example.com>") -> str:
    name, email = author[:-1].split(" <")
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
           "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "shop_api"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "старт", when="2026-10-01T10:00:00+00:00")
    return repo


def test_only_own_commits_in_the_period_are_taken(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "fix/a")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Мой фикс\n\nдетали", author="Me <Me@example.com>")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Чужой", author="Other <o@example.com>")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Мой старый", when="2026-10-05T10:00:00+00:00")

    commits = own_commits(repo, ["me@example.com"], START, END)

    assert [c.subject for c in commits] == ["Мой фикс"]
    assert commits[0].body == "детали"
    assert "fix/a" in commits[0].branches


def test_a_merge_into_dev_with_own_work_is_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feat/x")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Фича")
    _git(repo, "checkout", "-q", "dev")
    _git(repo, "merge", "-q", "--no-ff", "feat/x", "-m", "Merge branch 'feat/x' into 'dev'",
         when="2026-10-07T12:00:00+00:00", author="GitLab <gl@example.com>")

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
```

- [ ] **Step 2: Запустить** — `python3 -m pytest tests/test_repos.py -q` → FAIL.

- [ ] **Step 3: Реализация** — `scripts/repos.py`:
```python
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
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def repo_root(cwd: str) -> Path | None:
    path = Path(cwd)
    if not cwd or not path.is_dir():
        return None
    common = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None:
        return None
    common_dir = Path(common.strip())
    if common_dir.name == ".git":
        return common_dir.parent.resolve()
    top = _git(path, "rev-parse", "--show-toplevel")
    return Path(top.strip()).resolve() if top else None


def _author_args(authors: list[str]) -> list[str]:
    return ["--regexp-ignore-case", "--fixed-strings", *[f"--author={a}" for a in authors]]


def _range(start: datetime, end: datetime) -> list[str]:
    return [f"--since={start.isoformat()}", f"--until={end.isoformat()}"]


def own_commits(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Commit]:
    if not authors:
        return []
    out = _git(repo, "log", "--all", "--no-merges", *_range(start, end), *_author_args(authors),
               f"--format=%H{_FIELD}%aI{_FIELD}%s{_FIELD}%b{_RECORD}")
    commits = []
    for chunk in (out or "").split(_RECORD):
        parts = chunk.strip("\n").split(_FIELD)
        if len(parts) != 4:
            continue
        sha, at_raw, subject, body = parts
        at = parse_ts(at_raw)
        if at is None or not (start <= at < end):
            continue
        branches = (_git(repo, "branch", "-a", "--contains", sha, "--format=%(refname:short)") or "")
        commits.append(Commit(sha[:7], at, subject, "\n".join(body.strip().splitlines()[:3]),
                              [b for b in branches.split() if b][:3]))
    return sorted(commits, key=lambda c: c.at)


def own_merges(repo: Path, authors: list[str], start: datetime, end: datetime) -> list[Merge]:
    if not authors:
        return []
    merges: dict[str, Merge] = {}
    for target in _TARGETS:
        out = _git(repo, "log", target, "--first-parent", "--merges", *_range(start, end),
                   f"--format=%H{_FIELD}%aI{_FIELD}%s")
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
            merges[sha] = Merge(sha[:7], at, found.group(1) if found else subject,
                                target.removeprefix("origin/"))
    return sorted(merges.values(), key=lambda m: m.at)


def recent_authors(repo: Path, days: int) -> list[str]:
    out = _git(repo, "log", "--all", f"--since={days}.days", "--format=%an <%ae>")
    return [author for author, _ in Counter((out or "").splitlines()).most_common() if author]
```

- [ ] **Step 4: Запустить** — `python3 -m pytest tests/test_repos.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add plugins/work-report/skills/work-report/scripts/repos.py tests/test_repos.py
git commit -m "Выжимка: свои коммиты и merge из git, корень репозитория для worktree"
```

---

### Task 4: claude-mem как необязательный источник

**Files:**
- Create: `plugins/work-report/skills/work-report/scripts/mem.py`
- Test: `tests/test_mem.py`

**Interfaces:**
- Produces:
  - `mem.MemSummary(project: str, completed: str, next_steps: str, at: datetime)` — `project` уже без суффикса worktree (`shop_api/x` → `shop_api`);
  - `mem.read_summaries(db: Path, start: datetime, end: datetime) -> list[MemSummary] | None` — `None`, если источник недоступен по любой причине.

- [ ] **Step 1: Тест** — `tests/test_mem.py`:
```python
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mem import read_summaries

START = datetime(2026, 10, 7, tzinfo=timezone.utc)
END = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _db(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    con = sqlite3.connect(path)
    con.execute("create table session_summaries (project text, completed text, next_steps text,"
                " created_at text)")
    con.executemany("insert into session_summaries values (?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_summaries_inside_the_period_are_read(tmp_path: Path) -> None:
    db = _db(tmp_path / "m.db", [
        ("shop_api/wt", "Цикл заказа пройден", "Передать billing-api", "2026-10-07T10:00:00.000Z"),
        ("billing_api", "старое", "", "2026-10-01T10:00:00.000Z"),
    ])

    [summary] = read_summaries(db, START, END)

    assert (summary.project, summary.completed, summary.next_steps) == (
        "shop_api", "Цикл заказа пройден", "Передать billing-api")


def test_a_missing_database_or_table_means_no_source(tmp_path: Path) -> None:
    assert read_summaries(tmp_path / "nope.db", START, END) is None
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert read_summaries(empty, START, END) is None
```

- [ ] **Step 2: Запустить** — `python3 -m pytest tests/test_mem.py -q` → FAIL.

- [ ] **Step 3: Реализация** — `scripts/mem.py`:
```python
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
                " order by created_at", (since, until)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    found = []
    for project, completed, next_steps, created in rows:
        at = parse_ts(created)
        if at is None or not (completed.strip() or next_steps.strip()):
            continue
        found.append(MemSummary(str(project).split("/")[0], completed.strip(), next_steps.strip(), at))
    return found
```

- [ ] **Step 4: Запустить** — `python3 -m pytest tests/test_mem.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add plugins/work-report/skills/work-report/scripts/mem.py tests/test_mem.py
git commit -m "Выжимка: сводки claude-mem как необязательный источник"
```

---

### Task 5: Продукты, конфиг, сборка выжимки и CLI

**Files:**
- Create: `plugins/work-report/skills/work-report/scripts/products.py`
- Create: `plugins/work-report/skills/work-report/scripts/render.py`
- Create: `plugins/work-report/skills/work-report/scripts/digest.py`
- Create: `plugins/work-report/skills/work-report/reference/products.json`
- Test: `tests/test_products.py`, `tests/test_render.py`, `tests/test_digest_cli.py`

**Interfaces:**
- Consumes: всё из Task 1–4 (имена — как в их блоках Produces).
- Produces:
  - `products.load_products(shared: Path, personal: Path) -> dict[str, str]`; `products.product_for(repo_name: str, mapping: dict[str, str]) -> str` (`"unknown"`);
  - `render.Activity(repo_name: str, product: str, commits: list[Commit], merges: list[Merge], sessions: list[Session], mem: list[MemSummary])`;
  - `render.render(activities: list[Activity], start: date, end: date, sources: list[str], tz: tzinfo, limit: int = 2000) -> str`;
  - CLI `digest.py --from D --to D [--config P] [--claude-dir P] [--mem-db P] [--products P] [--tz IANA]` → выжимка в stdout, код 0; нет конфига → код 3 и подсказка; `digest.py --suggest-authors [--claude-dir P]` → JSON-список кандидатов `"Имя <email>"`.
  - Конфиг `~/work-reports/config.json`: `{"authors": [...], "reports_dir": "~/work-reports", "extra_repos": [...]}`.

- [ ] **Step 1: Тест продуктов** — `tests/test_products.py`:
```python
import json
from pathlib import Path

from products import load_products, product_for


def test_personal_entries_override_shared_and_unknown_is_marked(tmp_path: Path) -> None:
    shared = tmp_path / "shared.json"
    shared.write_text(json.dumps({"shop_api": "Магазин", "billing_api": "Биллинг"}), encoding="utf-8")
    personal = tmp_path / "personal.json"
    personal.write_text(json.dumps({"billing_api": "Счета"}), encoding="utf-8")

    mapping = load_products(shared, personal)

    assert product_for("shop_api", mapping) == "Магазин"
    assert product_for("billing_api", mapping) == "Счета"
    assert product_for("whatever", mapping) == "unknown"
    assert load_products(tmp_path / "no.json", tmp_path / "no2.json") == {}
```

- [ ] **Step 2: Тест рендера** — `tests/test_render.py`:
```python
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from render import Activity, render
from repos import Commit, Merge
from sessions import Session, Turn

TZ = ZoneInfo("Asia/Almaty")
AT = datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc)


def _session(n_turns: int, size: int) -> Session:
    turns = [Turn("user" if i % 2 == 0 else "assistant", f"{i} " + "x" * size, AT)
             for i in range(n_turns)]
    return Session("s1", "/r", "Проверка цикла", ["dev"], AT, AT, turns)


def test_digest_is_grouped_by_product_with_commits_merges_and_sessions() -> None:
    activity = Activity("shop_api", "Магазин",
                        [Commit("a1b2c3d", AT, "Отмена заказа", "", ["fix/cart"])],
                        [Merge("e4f5a6b", AT, "fix/cart", "dev")],
                        [_session(2, 10)], [])

    text = render([activity], date(2026, 10, 7), date(2026, 10, 7), ["git", "сессии"], TZ)

    assert text.splitlines()[0] == "# Выжимка 2026-10-07 — 2026-10-07"
    assert "источники: git, сессии" in text
    assert "## Магазин (shop_api)" in text
    assert "a1b2c3d 10-07 09:00 [fix/cart] Отмена заказа" in text
    assert "влито fix/cart → dev 10-07 09:00" in text
    assert "«Проверка цикла» [dev]" in text


def test_an_oversized_digest_is_cut_but_keeps_titles_and_session_outcomes() -> None:
    sessions = [_session(400, 900) for _ in range(5)]
    activity = Activity("shop_api", "Магазин", [], [], sessions, [])

    text = render([activity], date(2026, 10, 7), date(2026, 10, 7), ["git"], TZ, limit=300)

    assert len(text.splitlines()) <= 300
    assert text.count("«Проверка цикла»") == 5
    assert text.count("399 ") == 5  # last turn (outcome) of every session survives
```

- [ ] **Step 3: Тест CLI** — `tests/test_digest_cli.py` (сквозной на фейковых данных):
```python
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).parents[1] / "plugins/work-report/skills/work-report/scripts/digest.py")


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-10-07T10:00:00+05:00",
           "GIT_COMMITTER_DATE": "2026-10-07T10:00:00+05:00", "GIT_AUTHOR_NAME": "Me",
           "GIT_AUTHOR_EMAIL": "me@example.com", "GIT_COMMITTER_NAME": "Me",
           "GIT_COMMITTER_EMAIL": "me@example.com"}
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def _setup(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "shop_api"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "Полный цикл заказа, password=hunter2")
    claude = tmp_path / ".claude"
    folder = claude / "projects" / "p"
    folder.mkdir(parents=True)
    record = {"type": "user", "timestamp": "2026-10-07T05:00:00Z", "sessionId": "s1",
              "cwd": str(repo), "gitBranch": "dev", "isSidechain": False,
              "message": {"role": "user", "content": "давай пройдём цикл"}}
    (folder / "s1.jsonl").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"authors": ["me@example.com"], "reports_dir": str(tmp_path)}),
                      encoding="utf-8")
    products = tmp_path / "products.json"
    products.write_text(json.dumps({"shop_api": "Магазин"}), encoding="utf-8")
    return {"repo": repo, "claude": claude, "config": config, "products": products}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_digest_without_claude_mem_is_complete_and_masked(tmp_path: Path) -> None:
    p = _setup(tmp_path)

    done = _run("--from", "2026-10-07", "--to", "2026-10-07", "--config", str(p["config"]),
                "--claude-dir", str(p["claude"]), "--mem-db", str(tmp_path / "none.db"),
                "--products", str(p["products"]), "--tz", "Asia/Almaty")

    assert done.returncode == 0, done.stderr
    assert "источники: git, сессии\n" in done.stdout
    assert "## Магазин (shop_api)" in done.stdout
    assert "Полный цикл заказа" in done.stdout
    assert "давай пройдём цикл" in done.stdout
    assert "hunter2" not in done.stdout


def test_missing_config_exits_with_a_hint(tmp_path: Path) -> None:
    done = _run("--from", "2026-10-07", "--to", "2026-10-07",
                "--config", str(tmp_path / "missing.json"))

    assert done.returncode == 3
    assert "--suggest-authors" in done.stderr


def test_suggest_authors_lists_committers_of_session_repos(tmp_path: Path) -> None:
    p = _setup(tmp_path)

    done = _run("--suggest-authors", "--claude-dir", str(p["claude"]), "--days", "100000")

    assert done.returncode == 0, done.stderr
    assert "Me <me@example.com>" in json.loads(done.stdout)
```

- [ ] **Step 4: Запустить** — `python3 -m pytest tests/test_products.py tests/test_render.py tests/test_digest_cli.py -q` → FAIL.

- [ ] **Step 5: Реализация** — `scripts/products.py`:
```python
"""Repository name → product name for the report: shared map plus personal overrides."""

from __future__ import annotations

import json
from pathlib import Path

UNKNOWN = "unknown"


def _read(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def load_products(shared: Path, personal: Path) -> dict[str, str]:
    return {**_read(shared), **_read(personal)}


def product_for(repo_name: str, mapping: dict[str, str]) -> str:
    return mapping.get(repo_name, UNKNOWN)
```

`scripts/render.py`:
```python
"""The digest as Markdown, grouped by product, cut to a line limit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, tzinfo

from mem import MemSummary
from repos import Commit, Merge
from sessions import Session, Turn

# (max chars per turn, max turns kept per session or None) — tried in order until it fits.
_STEPS = ((800, None), (300, None), (150, None), (150, 8), (150, 2), (80, 2))


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
    return [turns[0], *turns[len(turns) - (keep - 1):]] if keep > 1 else turns[-1:]


def _lines(activities: list[Activity], start: date, end: date, sources: list[str], tz: tzinfo,
           chars: int, keep: int | None) -> list[str]:
    stamp = lambda at: at.astimezone(tz).strftime("%m-%d %H:%M")  # noqa: E731
    out = [f"# Выжимка {start.isoformat()} — {end.isoformat()}", f"источники: {', '.join(sources)}"]
    for act in sorted(activities, key=lambda a: -a.weight):
        out += ["", f"## {act.product} ({act.repo_name})"]
        if act.commits or act.merges:
            out.append("### Коммиты")
            out += [f"- {c.sha} {stamp(c.at)} [{', '.join(c.branches) or '—'}] {c.subject}"
                    + (f" — {_cut(c.body, 200)}" if c.body else "") for c in act.commits]
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
        if act.mem:
            out.append("### claude-mem")
            for m in act.mem:
                if m.completed:
                    out.append(f"- сделано: {_cut(m.completed, chars)}")
                if m.next_steps:
                    out.append(f"- дальше: {_cut(m.next_steps, chars)}")
    return out


def render(activities: list[Activity], start: date, end: date, sources: list[str], tz: tzinfo,
           limit: int = 2000) -> str:
    lines: list[str] = []
    for chars, keep in _STEPS:
        lines = _lines(activities, start, end, sources, tz, chars, keep)
        if len(lines) <= limit:
            break
    if len(lines) > limit:
        lines = lines[: limit - 1] + ["… (выжимка обрезана по лимиту)"]
    return "\n".join(lines) + "\n"
```

Примечание к `_turns`: при `keep=2` остаются первый вопрос и последний ход сессии (итог), что
и проверяет тест на обрезку.

`scripts/digest.py`:
```python
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
from zoneinfo import ZoneInfo

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
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"нет конфига {args.config}: сначала digest.py --suggest-authors и создать "
              "config.json с полем authors", file=sys.stderr)
        return EXIT_NO_CONFIG
    authors = [str(a) for a in config.get("authors", [])]
    reports_dir = Path(config.get("reports_dir", DEFAULT_REPORTS)).expanduser()
    tz = ZoneInfo(args.tz) if args.tz else datetime.now().astimezone().tzinfo
    start, end = period_bounds(args.start, args.end, tz)

    mapping = load_products(args.products, reports_dir / "products.json")
    sessions = collect_sessions(args.claude_dir, start, end)
    by_name: dict[str, Activity] = {}
    roots: dict[str, Path | None] = {}
    for s in sessions:
        root = repo_root(s.cwd)
        name = root.name if root else (Path(s.cwd).name or "без проекта")
        roots.setdefault(name, root)
        by_name.setdefault(name, Activity(name, product_for(name, mapping))).sessions.append(s)
    for extra in config.get("extra_repos", []):
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
```

`reference/products.json`:
```json
{
  "shop_api": "Магазин",
  "billing_api": "Биллинг",
  "work-report": "work-report"
}
```

- [ ] **Step 6: Запустить** — `python3 -m pytest -q` (весь набор) → PASS; `ruff check . && ruff format --check .`.

- [ ] **Step 7: Ручная проверка на своих данных** —
```bash
python3 plugins/work-report/skills/work-report/scripts/digest.py --suggest-authors
mkdir -p ~/work-reports && printf '{"authors": ["<из списка>"]}\n' > ~/work-reports/config.json
python3 plugins/work-report/skills/work-report/scripts/digest.py --from 2026-10-06 --to 2026-10-06 | head -80
```
Ожидаемо: группы Магазин / Биллинг, коммиты 06.10, сессии с заголовками; паролей и токенов нет.

- [ ] **Step 8: Commit**
```bash
git add plugins/work-report/skills/work-report tests
git commit -m "Выжимка: продукты, конфиг авторов, сборка по продуктам с лимитом и CLI"
```

---

### Task 6: Скилл, регламент, README, CI

**Files:**
- Create: `plugins/work-report/skills/work-report/SKILL.md`
- Create: `plugins/work-report/skills/work-report/reference/reglament.md`
- Create: `README.md`, `.gitlab-ci.yml`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: CLI `digest.py` из Task 5 (аргументы, коды 0/3, `--suggest-authors`).

- [ ] **Step 1: Тест файлов скилла** — `tests/test_skill_files.py`:
```python
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SKILL = ROOT / "plugins/work-report/skills/work-report"


def test_skill_frontmatter_and_script_path() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert text.startswith("---\nname: work-report\n")
    assert "description:" in text.split("---")[1]
    assert "${CLAUDE_PLUGIN_ROOT}/skills/work-report/scripts/digest.py" in text
    assert "reference/reglament.md" in text


def test_manifests_agree_on_name_and_version() -> None:
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    plugin = json.loads((ROOT / "plugins/work-report/.claude-plugin/plugin.json").read_text())

    assert marketplace["plugins"][0]["name"] == plugin["name"] == "work-report"
    assert marketplace["plugins"][0]["source"] == "./plugins/work-report"
    assert plugin["version"]


def test_reglament_carries_the_four_part_blocker_rule() -> None:
    text = (SKILL / "reference/reglament.md").read_text(encoding="utf-8")

    for word in ("От кого", "До", "Последствие", "РИСК СРОКА", "не более 5"):
        assert word in text
```

- [ ] **Step 2: Запустить** — `python3 -m pytest tests/test_skill_files.py -q` → FAIL.

- [ ] **Step 3: `SKILL.md`**:
````markdown
---
name: work-report
description: Карточки выполненных задач за день для таск-трекера и недельный отчёт по регламенту — из git и истории сессий Claude Code. Вызывать в конце дня (/work-report [YYYY-MM-DD]) и в пятницу (/work-report week).
---

# work-report

Аргументы: `$ARGUMENTS` — пусто (сегодня), дата `YYYY-MM-DD` или `week`.

Скрипт: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/work-report/scripts/digest.py"`.
Журнал: `reports_dir` из `~/work-reports/config.json` (по умолчанию `~/work-reports`).

## 0. Первый запуск
Если `~/work-reports/config.json` нет (скрипт вернул код 3):
1. Запусти скрипт с `--suggest-authors`, покажи список и спроси, какие из этих
   «Имя <email>» — пользователь (их может быть несколько: машинный email, рабочий, GitLab).
2. Запиши `~/work-reports/config.json`: `{"authors": [...], "reports_dir": "~/work-reports", "extra_repos": []}`.

## 1. Режим «день» (нет аргумента или дата)
1. Дата = аргумент или сегодня. Запусти `digest.py --from <дата> --to <дата>`.
2. Для групп `unknown` спроси название продукта и допиши в `<reports_dir>/products.json`.
3. Сгруппируй работу в **крупные задачи**: одна карточка — один законченный результат;
   связанные коммиты и сессии одной темы — в одну карточку; мелочи — в соседнюю.
   Результат, а не процесс («сделано X», а не «работал над X»).
4. Формат каждой карточки — ровно такой:
   ```
   **Заголовок:** <короткий результат>
   **Описание:**
   Что сделать: <что сделано/что требовалось>
   Зачем: <проблема, которую это решает>
   Как проверить: <ручки, тесты, ID, ответы систем из выжимки>
   ```
5. Незаконченное (нет merge, тест красный, ждём ответа) — допиши в заголовок «(в работе)»
   и строку `Осталось: …`.
6. **Никогда** не переноси в карточки пароли, токены, ключи, персональные данные.
7. Покажи карточки. Сохрани в `<reports_dir>/<дата>.md` (заголовок `# <дата>`); если файл
   есть — спроси: перезаписать или дополнить.

## 2. Режим «неделя» (`week`)
1. Неделя: пн–пт текущей недели; в сб/вс — только что закончившейся.
2. Прочитай `<reports_dir>/<дата>.md` за каждый день пн–пт. Для отсутствующих дней запусти
   `digest.py` за этот день и скажи, какие дни добраны так.
3. Прочитай `reference/reglament.md` и напиши отчёт строго по нему: три поля, группировка по
   продуктам, ≤ 5 пунктов на продукт в «сделано» и «планах», строка ≤ ~160 символов, `[#…]`
   вместо номера задачи.
4. «Планы» — из незаконченного за неделю (и строк «дальше» claude-mem, если есть).
   «Проблемы и блокеры» — только реальные препятствия, каждый из четырёх элементов; если
   «От кого»/«До» неизвестны — `___` и явная просьба пользователю заполнить до сдачи.
5. Сохрани в `<reports_dir>/week-<понедельник>.md`.

## Чего не делать
- Не отправлять ничего в таск-трекер — только текст.
- Не выдумывать работу, которой нет в выжимке или дневных файлах.
````

- [ ] **Step 4: `reference/reglament.md`** — перенести правила регламента полным текстом:
````markdown
# Регламент еженедельной отчётности (выдержка для скилла)

Схема Progress / Plans / Problems: «сделано / план / блокеры». Один отчёт на человека за
неделю, все продукты внутри. Сдаётся в пятницу в таск-трекер. Отчёт
сдаётся за неделю, которая заканчивается.

## Поля
| Поле | Обяз. | Что пишется |
|---|---|---|
| Что сделано за неделю | Да | Результаты, доведённые до состояния, которым можно пользоваться или которое можно проверить |
| Планы на следующую неделю | Да | То, что реально берётся в работу на следующей неделе |
| Проблемы и блокеры | Нет | Только реальные препятствия и нужные решения. Пустое поле = блокеров нет |

## Группировка по продуктам
Внутри каждого поля: название продукта, двоеточие, под ним пункты. Если по продукту риск
срока или работа стоит — пометка в строке продукта («OFD — РИСК СРОКА:»). «В графике» не пишется.

## «Что сделано» — результат, а не процесс
Проверка: по строке понятно, что теперь можно делать такого, чего нельзя было в понедельник.
Каждая строка — с номером задачи `[#…]`; содержимое задачи не пересказывается.
Не «Работал над авторизацией» → «Авторизация по PIN готова, передана QA [#142]».
Незавершённое — с процентом готовности и тем, что осталось.

## «Планы»
Только то, что реально берётся в работу. Продукт без работы на следующей неделе — одна
строка с причиной: «Pharma: на паузе, приоритет на OFD».

## «Проблемы и блокеры»
Блокер — четыре элемента: что мешает, От кого нужно действие, До какой даты, Последствие.
Блокер без адресата и даты — жалоба. Сюда же — решения, которые сотрудник не может принять сам.
```
OFD:
- Нет доступа к тестовому контуру КГД
  От кого: Даулет
  До: 10.09
  Последствие: сдвиг релиза на 5 дней
```

## Объём
- не более 5 пунктов на продукт в «Сделано» и не более 5 в «Планы»;
- один пункт — одна строка, примерно до 160 символов;
- развёрнуто пишется только блокер.

## Частые ошибки
- задачи вместо результатов: «делал», «продолжал», «занимался»;
- всё одним списком без разбивки по продуктам;
- блокер без адресата и даты;
- «всё хорошо» в «Проблемах» вместо пустого поля;
- планы на десять пунктов, из которых выполнимы три.

## Пример
```
Что сделано за неделю
POS:
- Оплата картой через эквайринг: готово, передано QA [#142]
OFD — РИСК СРОКА:
- Очередь отправки чеков в КГД: 70%, осталась обработка повторных попыток [#151]

Планы на следующую неделю
OFD:
- Дописать ретраи, отдать на нагрузочное тестирование
Pharma: на паузе, приоритет на OFD

Проблемы и блокеры
OFD:
- Нет доступа к тестовому контуру КГД
  От кого: Даулет
  До: 10.09
  Последствие: сдвиг релиза на 5 дней
```
````

- [ ] **Step 5: `README.md`** — установка (`/plugin marketplace add <git-url>`,
`/plugin install work-report@work-report`, обновление `/plugin update work-report@work-report`),
вызов (`/work-report`, `/work-report 2026-10-06`, `/work-report week`; при конфликте имён —
`/work-report:work-report`), первый запуск (авторы), где журнал, как добавить продукт в общий
словарь (MR в `reference/products.json`), разработка (`python3 -m pytest`, `ruff check .`,
`claude plugin validate .`), эталонные примеры дня и недели (заполняет автор после первого
реального прогона — раздел с пометкой «пример»).

- [ ] **Step 6: `.gitlab-ci.yml`**:
```yaml
test:
  image: python:3.12-slim
  before_script:
    - apt-get update -qq && apt-get install -y -qq git >/dev/null
    - pip install -q pytest ruff
  script:
    - ruff check .
    - ruff format --check .
    - python -m pytest -q
```

- [ ] **Step 7: Запустить** — `python3 -m pytest -q` → PASS; `ruff check . && ruff format --check .`;
если установлен Claude Code CLI: `claude plugin validate .` → exit 0.

- [ ] **Step 8: Commit**
```bash
git add plugins/work-report/skills/work-report/SKILL.md plugins/work-report/skills/work-report/reference/reglament.md README.md .gitlab-ci.yml tests/test_skill_files.py
git commit -m "Скилл work-report: режимы день и неделя, регламент, README и CI"
```

---

## После всех задач
- [ ] Локальная установка для проверки: `/plugin marketplace add ~/Documents/PythonProjects/work-report`,
      `/plugin install work-report@work-report`, вызвать `/work-report 2026-10-06` и
      `/work-report week`; результат показать автору, лучшие примеры — в README.
- [ ] Review всей ветки; push в GitLab — после создания репозитория пользователем и по его команде.
