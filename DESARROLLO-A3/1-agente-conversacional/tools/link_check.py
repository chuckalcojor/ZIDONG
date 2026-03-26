import json
import os
from urllib import error, parse, request


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def fetch_json(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        payload = {"error": body}
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            pass
        return exc.code, payload


def check_telegram() -> dict:
    token = env("TELEGRAM_BOT_TOKEN")
    status, payload = fetch_json(f"https://api.telegram.org/bot{token}/getMe")
    ok = bool(payload.get("ok")) and status == 200
    return {
        "ok": ok,
        "http_status": status,
        "bot_username": payload.get("result", {}).get("username"),
        "bot_id": payload.get("result", {}).get("id"),
    }


def check_supabase() -> dict:
    base_url = env("SUPABASE_URL").rstrip("/")
    service_role = env("SUPABASE_SERVICE_ROLE_KEY")

    query = parse.urlencode({"select": "id", "limit": "1"})
    url = f"{base_url}/rest/v1/clients?{query}"
    headers = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
    }
    status, payload = fetch_json(url, headers=headers)

    table_ready = status == 200
    return {
        "ok": status in {200, 404},
        "http_status": status,
        "table_ready": table_ready,
        "note": (
            "clients table reachable"
            if table_ready
            else "clients table not found or inaccessible; run SQL schema"
        ),
        "raw": payload,
    }


def main() -> None:
    load_dotenv()
    result = {
        "telegram": check_telegram(),
        "supabase": check_supabase(),
    }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
