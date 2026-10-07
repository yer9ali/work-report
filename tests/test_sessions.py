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
    return {
        "type": "user",
        "timestamp": ts,
        "sessionId": "s1",
        "cwd": "/repo/a",
        "gitBranch": "dev",
        "isSidechain": False,
        "message": {"role": "user", "content": text},
        **extra,
    }


def _assistant(ts: str, text: str, **extra: object) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "sessionId": "s1",
        "cwd": "/repo/a",
        "gitBranch": "dev",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "x"}, {"type": "text", "text": text}],
        },
        **extra,
    }


def _day(d: date):
    return period_bounds(d, d, ALMATY)


def test_a_session_keeps_real_user_text_and_the_last_answer_of_each_turn(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "p",
        "s1",
        [
            _user("2026-10-07T04:00:00Z", "давай пройдём цикл"),
            _assistant("2026-10-07T04:00:05Z", "промежуточный ответ"),
            _user("2026-10-07T04:00:06Z", [{"type": "tool_result", "content": "лог"}]),
            _assistant("2026-10-07T04:00:09Z", "Цикл прошёл"),
            _user("2026-10-07T04:01:00Z", "Base directory for this skill: /x", isMeta=True),
            {"type": "ai-title", "aiTitle": "Проверка цикла заказа", "sessionId": "s1"},
            "{битая строка",
        ],
    )

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert session.title == "Проверка цикла заказа"
    assert session.cwd == "/repo/a"
    assert session.branches == ["dev"]
    assert [(t.role, t.text) for t in session.turns] == [
        ("user", "давай пройдём цикл"),
        ("assistant", "Цикл прошёл"),
    ]


def test_only_records_inside_the_local_day_are_taken(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "p",
        "s1",
        [
            _user("2026-10-06T18:30:00Z", "вчера 23:30 по Алматы"),
            _assistant("2026-10-06T18:31:00Z", "вчерашний ответ"),
            _user("2026-10-06T19:30:00Z", "сегодня 00:30 по Алматы"),
            _assistant("2026-10-06T19:31:00Z", "сегодняшний ответ"),
        ],
    )

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert [t.text for t in session.turns] == ["сегодня 00:30 по Алматы", "сегодняшний ответ"]


def test_subagents_and_service_tags_are_left_out(tmp_path: Path) -> None:
    long_paste = '<pasted_content id="x">' + "z" * 5000 + '</pasted_content id="x">'
    _write(
        tmp_path,
        "p",
        "s1",
        [
            _user(
                "2026-10-07T04:00:00Z", "<system-reminder>шум</system-reminder>смотри " + long_paste
            ),
            _user("2026-10-07T04:00:01Z", "<bash-input>git status</bash-input>"),
            _assistant("2026-10-07T04:00:02Z", "ответ субагента", isSidechain=True),
        ],
    )

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    texts = [t.text for t in session.turns]
    assert texts[0].startswith("смотри [вставка")
    assert "шум" not in texts[0]
    assert texts[1] == "! git status"
    assert all("субагента" not in t for t in texts)


def test_a_session_outside_the_period_is_not_returned(tmp_path: Path) -> None:
    _write(tmp_path, "p", "s1", [_user("2026-10-01T04:00:00Z", "давно")])

    assert collect_sessions(tmp_path, *_day(date(2026, 10, 7))) == []


def test_empty_bash_input_gives_no_turn_and_does_not_crash(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "p",
        "s1",
        [
            _user("2026-10-07T04:00:00Z", "<bash-input></bash-input>"),
            _user("2026-10-07T04:00:01Z", "<bash-input>  \n </bash-input>"),
            _user("2026-10-07T04:00:02Z", "нормальный вопрос"),
        ],
    )

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert [t.text for t in session.turns] == ["нормальный вопрос"]


def test_service_command_tags_are_dropped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "p",
        "s1",
        [
            _user("2026-10-07T04:00:00Z", "<local-command-caveat>Caveat</local-command-caveat>"),
            _user(
                "2026-10-07T04:00:01Z",
                "<command-name>/clear</command-name><command-message>clear</command-message>"
                "<command-args></command-args>",
            ),
            _user("2026-10-07T04:00:02Z", "<local-command-stdout>вывод</local-command-stdout>"),
            _user("2026-10-07T04:00:03Z", "вопрос"),
        ],
    )

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert [t.text for t in session.turns] == ["вопрос"]


def test_an_unreadable_file_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "p", "s1", [_user("2026-10-07T04:00:00Z", "живая")])
    (tmp_path / "projects" / "p" / "x.jsonl").mkdir()

    [session] = collect_sessions(tmp_path, *_day(date(2026, 10, 7)))

    assert [t.text for t in session.turns] == ["живая"]
