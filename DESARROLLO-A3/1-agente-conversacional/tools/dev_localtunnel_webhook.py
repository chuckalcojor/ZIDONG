from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


URL_LINE_RE = re.compile(r"your url is:\s*(https://\S+)", re.IGNORECASE)


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    output: list[str] = []
    replaced = False
    prefix = f"{key}="

    for line in lines:
        if line.startswith(prefix):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)

    if not replaced:
        output.append(f"{key}={value}")

    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def set_webhook(token: str, secret: str, webhook_url: str) -> dict:
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={
            "url": webhook_url,
            "secret_token": secret,
            "drop_pending_updates": True,
            "allowed_updates": ["message", "edited_message"],
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def get_webhook_info(token: str) -> dict:
    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getWebhookInfo",
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start localtunnel, register Telegram webhook, and persist URL in .env",
    )
    parser.add_argument("--port", type=int, default=8000, help="Local Flask port")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file where TELEGRAM_WEBHOOK_URL is stored",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(args.env_file)

    token = env("TELEGRAM_BOT_TOKEN")
    secret = env("TELEGRAM_WEBHOOK_SECRET")
    env_path = Path(args.env_file)

    npx_bin = "npx.cmd" if os.name == "nt" else "npx"

    process = subprocess.Popen(
        [npx_bin, "--yes", "localtunnel", "--port", str(args.port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def stop_child(*_: object) -> None:
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGINT, stop_child)
    signal.signal(signal.SIGTERM, stop_child)

    webhook_registered = False

    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            print(line)

            if webhook_registered:
                continue

            match = URL_LINE_RE.search(line)
            if not match:
                continue

            public_url = match.group(1).rstrip("/")
            webhook_url = f"{public_url}/webhooks/telegram"

            upsert_env_var(env_path, "TELEGRAM_WEBHOOK_URL", webhook_url)
            set_result = set_webhook(token, secret, webhook_url)
            info_result = get_webhook_info(token)

            print("[webhook] registered")
            print(json.dumps({"setWebhook": set_result, "getWebhookInfo": info_result}, ensure_ascii=True))
            webhook_registered = True

        if not webhook_registered:
            raise RuntimeError("Could not read public URL from localtunnel output")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"dev_localtunnel_webhook error: {exc}", file=sys.stderr)
        sys.exit(1)
