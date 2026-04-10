import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.logic import assign_courier


def main() -> None:
    payload = json.load(sys.stdin)
    result = assign_courier(payload)
    json.dump(result, sys.stdout, ensure_ascii=True)


if __name__ == "__main__":
    main()
