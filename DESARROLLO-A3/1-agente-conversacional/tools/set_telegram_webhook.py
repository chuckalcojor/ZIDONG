import os

import httpx


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    webhook_url = os.environ["TELEGRAM_WEBHOOK_URL"]
    secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]

    url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": secret,
        "drop_pending_updates": True,
    }

    response = httpx.post(url, json=payload, timeout=20)
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
