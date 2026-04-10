import httpx


class WhatsAppService:
    def __init__(self, access_token: str, phone_number_id: str) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.base_url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"

    def send_text(self, to: str, text: str) -> None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        with httpx.Client(timeout=20) as client:
            response = client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
