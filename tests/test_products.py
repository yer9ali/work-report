import json
from pathlib import Path

from products import load_products, product_for


def test_personal_entries_override_shared_and_unknown_is_marked(tmp_path: Path) -> None:
    shared = tmp_path / "shared.json"
    shared.write_text(
        json.dumps({"shop_api": "Магазин", "billing_api": "Биллинг"}), encoding="utf-8"
    )
    personal = tmp_path / "personal.json"
    personal.write_text(json.dumps({"billing_api": "Счета"}), encoding="utf-8")

    mapping = load_products(shared, personal)

    assert product_for("shop_api", mapping) == "Магазин"
    assert product_for("billing_api", mapping) == "Счета"
    assert product_for("whatever", mapping) == "unknown"
    assert load_products(tmp_path / "no.json", tmp_path / "no2.json") == {}
