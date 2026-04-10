import httpx


class TelegramService:
    def __init__(self, bot_token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, chat_id: int, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text}
        with httpx.Client(timeout=20) as client:
            response = client.post(f"{self.base_url}/sendMessage", json=payload)
            response.raise_for_status()
