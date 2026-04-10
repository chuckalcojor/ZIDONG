from __future__ import annotations

import json
import sys
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "http://localhost:8000"


def request(opener, method: str, path: str, data: dict[str, str] | None = None) -> tuple[int, str]:
    body = None
    headers = {}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(f"{BASE_URL}{path}", data=body, method=method, headers=headers)
    with opener.open(req, timeout=15) as response:
        return response.status, response.geturl()


def post_json(opener, path: str, payload: dict) -> int:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{BASE_URL}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=15) as response:
        return response.status


def main() -> int:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    checks: list[tuple[str, bool, str]] = []

    status, _ = request(opener, "GET", "/health")
    checks.append(("health", status == 200, f"status={status}"))

    status, redirect_url = request(
        opener,
        "POST",
        "/login",
        {"username": "admin", "password": "admin123"},
    )
    checks.append(("login", status in {200, 302}, f"status={status} url={redirect_url}"))

    for path in [
        "/dashboard",
        "/clientes",
        "/muestras",
        "/analisis",
        "/flujo",
        "/aprobaciones",
        "/afiliaciones",
    ]:
        status, _ = request(opener, "GET", path)
        checks.append((path, status == 200, f"status={status}"))

    status, _ = request(
        opener,
        "POST",
        "/aprobaciones/decision",
        {
            "external_chat_id": "99001",
            "decision": "reject",
            "reason": "Prueba QA",
            "q": "",
            "profile": "all",
            "since": "",
        },
    )
    checks.append(("approval_decision", status in {200, 302}, f"status={status}"))

    wa_status = post_json(
        opener,
        "/webhooks/whatsapp",
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "573001112233",
                                        "type": "text",
                                        "text": {"body": "hola"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        },
    )
    checks.append(("whatsapp_webhook", wa_status == 200, f"status={wa_status}"))

    failed = [item for item in checks if not item[1]]
    for name, ok, info in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {name} -> {info}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
