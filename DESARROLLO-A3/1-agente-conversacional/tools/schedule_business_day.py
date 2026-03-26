import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.logic import calculate_schedule


def main() -> None:
    payload = json.load(sys.stdin)
    received_at = payload["received_at"]
    cutoff = payload.get("cutoff", "17:30")
    result = calculate_schedule(received_at, cutoff)
    json.dump(result, sys.stdout, ensure_ascii=True)


if __name__ == "__main__":
    main()
