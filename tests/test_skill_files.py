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


def test_tracker_config_maps_products_to_ids() -> None:
    tracker = json.loads((SKILL / "reference/tracker.json").read_text(encoding="utf-8"))

    assert tracker["url"].startswith("https://")
    for ids in tracker["products"].values():
        assert isinstance(ids["client_id"], int) and isinstance(ids["product_id"], int)
