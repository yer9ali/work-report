"""Repository name → product name for the report: shared map plus personal overrides."""

from __future__ import annotations

import json
from pathlib import Path


def _read(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def load_products(shared: Path, personal: Path) -> dict[str, str]:
    return {**_read(shared), **_read(personal)}


def product_for(repo_name: str, mapping: dict[str, str]) -> str:
    return mapping.get(repo_name, repo_name)
