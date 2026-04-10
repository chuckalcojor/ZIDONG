from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _mock_file_path() -> Path:
    base_dir = Path(__file__).resolve().parents[3]
    return base_dir / "2-plataforma" / "mock-data" / "dashboard_context.json"


def load_mock_dashboard_context() -> dict[str, Any]:
    mock_path = _mock_file_path()
    if not mock_path.exists():
        raise RuntimeError(
            "Mock dashboard data file not found. Expected: "
            f"{mock_path}"
        )

    with mock_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise RuntimeError("Mock dashboard data must be a JSON object")

    return payload
