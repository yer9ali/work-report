import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mem import read_summaries

START = datetime(2026, 10, 7, tzinfo=timezone.utc)
END = datetime(2026, 10, 8, tzinfo=timezone.utc)


def _db(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    con = sqlite3.connect(path)
    con.execute(
        "create table session_summaries (project text, completed text, next_steps text,"
        " created_at text)"
    )
    con.executemany("insert into session_summaries values (?,?,?,?)", rows)
    con.commit()
    con.close()
    return path


def test_summaries_inside_the_period_are_read(tmp_path: Path) -> None:
    db = _db(
        tmp_path / "m.db",
        [
            (
                "shop_api/wt",
                "Цикл заказа пройден",
                "Передать billing-api",
                "2026-10-07T10:00:00.000Z",
            ),
            ("billing_api", "старое", "", "2026-10-01T10:00:00.000Z"),
        ],
    )

    [summary] = read_summaries(db, START, END)

    assert (summary.project, summary.completed, summary.next_steps) == (
        "shop_api",
        "Цикл заказа пройден",
        "Передать billing-api",
    )


def test_a_missing_database_or_table_means_no_source(tmp_path: Path) -> None:
    assert read_summaries(tmp_path / "nope.db", START, END) is None
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert read_summaries(empty, START, END) is None
