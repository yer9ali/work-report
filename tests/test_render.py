from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from mem import MemSummary
from render import Activity, render
from repos import Commit, Merge
from sessions import Session, Turn

TZ = ZoneInfo("Asia/Almaty")
AT = datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc)


def _session(n_turns: int, size: int) -> Session:
    turns = [
        Turn("user" if i % 2 == 0 else "assistant", f"{i} " + "x" * size, AT)
        for i in range(n_turns)
    ]
    return Session("s1", "/r", "Проверка цикла", ["dev"], AT, AT, turns)


def test_digest_is_grouped_by_product_with_commits_merges_and_sessions() -> None:
    activity = Activity(
        "shop_api",
        "Магазин",
        [Commit("a1b2c3d", AT, "Отмена заказа", "", ["fix/cart"])],
        [Merge("e4f5a6b", AT, "fix/cart", "dev")],
        [_session(2, 10)],
        [],
    )

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


def test_a_flood_of_claude_mem_summaries_does_not_push_out_session_titles_and_outcomes() -> None:
    sessions = [_session(6, 50) for _ in range(5)]
    mem = [MemSummary("shop_api", f"сделано {i} " + "y" * 500, "дальше", AT) for i in range(95)]
    activity = Activity("shop_api", "Магазин", [], [], sessions, mem)

    text = render([activity], date(2026, 10, 7), date(2026, 10, 7), ["git"], TZ, limit=100)

    assert len(text.splitlines()) <= 100
    assert text.count("«Проверка цикла»") == 5
    assert text.count("5 x") == 5  # last turn of every session survives


def test_unmapped_repo_is_titled_by_its_name_once() -> None:
    activity = Activity("promo_bar", "promo_bar", [], [], [_session(2, 10)], [])

    text = render([activity], date(2026, 10, 7), date(2026, 10, 7), ["git"], TZ)

    assert "\n## promo_bar\n" in text
