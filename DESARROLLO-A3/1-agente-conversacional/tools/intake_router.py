import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.logic import route_message


def main() -> None:
    payload = json.load(sys.stdin)
    message = payload.get("message", "")
    result = route_message(message)
    json.dump(result, sys.stdout, ensure_ascii=True)


if __name__ == "__main__":
    main()
