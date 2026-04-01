from __future__ import annotations

from typing import Any

import httpx


class SupabaseService:
    def __init__(self, base_url: str, service_role_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def _rest_url(self, table: str) -> str:
        return f"{self.base_url}/rest/v1/{table}"

    def fetch_rows(self, table: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30) as client:
            response = client.get(self._rest_url(table), headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    def insert_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        headers = {**self.headers, "Prefer": "return=representation"}
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        params: dict[str, str] = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        with httpx.Client(timeout=45) as client:
            response = client.post(
                self._rest_url(table),
                headers=headers,
                params=params,
                json=rows,
            )
            response.raise_for_status()
            return response.json()

    def count_rows(self, table: str) -> int:
        headers = {**self.headers, "Prefer": "count=exact", "Range": "0-0"}
        params = {"select": "id"}
        with httpx.Client(timeout=20) as client:
            response = client.get(self._rest_url(table), headers=headers, params=params)
            response.raise_for_status()
            content_range = response.headers.get("Content-Range", "0-0/0")
            total = content_range.split("/")[-1]
            try:
                return int(total)
            except ValueError:
                return 0

    def update_rows(
        self,
        table: str,
        filters: dict[str, str],
        payload: dict[str, Any],
    ) -> None:
        with httpx.Client(timeout=30) as client:
            response = client.patch(
                self._rest_url(table),
                headers=self.headers,
                params=filters,
                json=payload,
            )
            response.raise_for_status()

    def delete_rows(self, table: str, filters: dict[str, str]) -> int:
        headers = {**self.headers, "Prefer": "count=exact"}
        with httpx.Client(timeout=30) as client:
            response = client.delete(
                self._rest_url(table),
                headers=headers,
                params=filters,
            )
            response.raise_for_status()
            content_range = response.headers.get("Content-Range", "0-0/0")
            total = content_range.split("/")[-1]
            try:
                return int(total)
            except ValueError:
                return 0

    def get_client_by_phone(self, phone: str) -> dict[str, Any] | None:
        params = {"phone": f"eq.{phone}", "select": "id,clinic_name,phone"}
        with httpx.Client(timeout=20) as client:
            response = client.get(self._rest_url("clients"), headers=self.headers, params=params)
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return None
            return rows[0]

    def get_client_by_tax_id(self, tax_id: str) -> dict[str, Any] | None:
        params = {
            "tax_id": f"eq.{tax_id}",
            "select": "id,clinic_name,phone,tax_id",
            "limit": "1",
        }
        with httpx.Client(timeout=20) as client:
            response = client.get(self._rest_url("clients"), headers=self.headers, params=params)
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return None
            return rows[0]

    def search_clients_by_clinic_name(self, clinic_name: str, limit: int = 5) -> list[dict[str, Any]]:
        safe_name = (clinic_name or "").replace("%", "").replace("_", "").strip()
        if not safe_name:
            return []
        params = {
            "clinic_name": f"ilike.*{safe_name}*",
            "select": "id,clinic_name,phone,tax_id",
            "order": "clinic_name.asc",
            "limit": str(limit),
        }
        return self.fetch_rows("clients", params)

    def get_assigned_courier_id(self, client_id: str) -> str | None:
        params = {
            "client_id": f"eq.{client_id}",
            "select": "courier_id",
            "limit": "1",
        }
        with httpx.Client(timeout=20) as client:
            response = client.get(
                self._rest_url("client_courier_assignment"),
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return None
            return rows[0].get("courier_id")

    def get_assigned_courier(self, client_id: str) -> dict[str, Any] | None:
        params = {
            "client_id": f"eq.{client_id}",
            "select": "courier_id,couriers(id,name,phone,availability)",
            "limit": "1",
        }
        rows = self.fetch_rows("client_courier_assignment", params)
        if not rows:
            return None
        courier = rows[0].get("couriers") or {}
        if isinstance(courier, dict) and courier.get("id"):
            return courier
        return None

    def create_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {**self.headers, "Prefer": "return=representation"}
        with httpx.Client(timeout=20) as client:
            response = client.post(self._rest_url("requests"), headers=headers, json=payload)
            response.raise_for_status()
            return response.json()[0]

    def update_request(self, request_id: str, payload: dict[str, Any]) -> None:
        params = {"id": f"eq.{request_id}"}
        with httpx.Client(timeout=20) as client:
            response = client.patch(
                self._rest_url("requests"),
                headers=self.headers,
                params=params,
                json=payload,
            )
            response.raise_for_status()

    def create_request_event(
        self, request_id: str, event_type: str, event_payload: dict[str, Any]
    ) -> None:
        payload = {
            "request_id": request_id,
            "event_type": event_type,
            "event_payload": event_payload,
        }
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self._rest_url("request_events"),
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()

    def list_clients_with_assignment(self) -> list[dict[str, Any]]:
        params = {
            "select": "id,clinic_name,phone,address,zone,billing_type,is_active,client_courier_assignment(courier_id,couriers(id,name,phone,availability))",
            "order": "clinic_name.asc",
            "limit": "2000",
        }
        return self.fetch_rows("clients", params)

    def list_requests(self, limit: int = 2000) -> list[dict[str, Any]]:
        params = {
            "select": "id,client_id,service_area,intent,priority,status,scheduled_pickup_date,assigned_courier_id,created_at,updated_at,fallback_reason,clients(clinic_name),couriers(name)",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("requests", params)

    def list_recent_conversations(self, limit: int = 200) -> list[dict[str, Any]]:
        params = {
            "select": "id,channel,external_contact,customer_name,last_message_at,open_status,conversation_summary",
            "order": "last_message_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("liveconnect_conversations", params)

    def list_recent_messages(self, limit: int = 300) -> list[dict[str, Any]]:
        params = {
            "select": "id,conversation_id,direction,message_text,created_at,agent_name,intent_tag",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("liveconnect_messages", params)

    def list_catalog_tests(self, limit: int = 3000) -> list[dict[str, Any]]:
        params = {
            "select": "id,test_code,test_name,category,subcategory,price_cop,turnaround_hours,sample_type,is_active",
            "order": "test_code.asc",
            "limit": str(limit),
        }
        return self.fetch_rows("analysis_catalog", params)

    def search_a3_knowledge_by_clinic_name(
        self, clinic_name: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        safe_name = (clinic_name or "").replace("%", "").replace("_", "").strip()
        if not safe_name:
            return []
        params = {
            "clinic_name": f"ilike.*{safe_name}*",
            "select": "clinic_key,clinic_name,is_registered,is_new_client,address,locality,phone,email,payment_policy,result_delivery_mode",
            "order": "clinic_name.asc",
            "limit": str(limit),
        }
        return self.fetch_rows("clients_a3_knowledge", params)

    def list_a3_professionals(self, clinic_key: str, limit: int = 20) -> list[dict[str, Any]]:
        params = {
            "clinic_key": f"eq.{clinic_key}",
            "select": "professional_name,professional_card,source_sheet",
            "order": "professional_name.asc",
            "limit": str(limit),
        }
        return self.fetch_rows("clients_a3_professionals", params)

    def list_a3_sample_events(self, clinic_key: str, limit: int = 200) -> list[dict[str, Any]]:
        params = {
            "clinic_key": f"eq.{clinic_key}",
            "select": "status_bucket,reason,patient_name,exam_number,pending_exam,source_sheet,synced_at",
            "order": "synced_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("clients_a3_sample_events", params)

    def get_telegram_session(self, chat_id: str) -> dict[str, Any] | None:
        params = {
            "external_chat_id": f"eq.{chat_id}",
            "select": "*",
            "limit": "1",
        }
        with httpx.Client(timeout=20) as client:
            response = client.get(
                self._rest_url("telegram_sessions"),
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            rows = response.json()
            if not rows:
                return None
            return rows[0]

    def upsert_telegram_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        params = {"on_conflict": "external_chat_id"}
        with httpx.Client(timeout=25) as client:
            response = client.post(
                self._rest_url("telegram_sessions"),
                headers=headers,
                params=params,
                json=[payload],
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0]

    def create_conversation_stage_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {**self.headers, "Prefer": "return=representation"}
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self._rest_url("conversation_stage_events"),
                headers=headers,
                json=[payload],
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0]

    def list_recent_conversation_stage_events(self, limit: int = 500) -> list[dict[str, Any]]:
        params = {
            "select": "id,channel,external_chat_id,client_id,request_id,from_stage,to_stage,trigger_source,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("conversation_stage_events", params)

    def list_telegram_sessions_with_client(self, limit: int = 2000) -> list[dict[str, Any]]:
        params = {
            "select": "id,external_chat_id,client_id,phase_current,status,requires_handoff,handoff_area,updated_at,last_user_message,last_bot_message,clients(clinic_name,phone)",
            "order": "updated_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("telegram_sessions", params)

    def create_telegram_message_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {**self.headers, "Prefer": "return=representation"}
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self._rest_url("telegram_message_events"),
                headers=headers,
                json=[payload],
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0]

    def list_telegram_message_events(
        self, external_chat_id: str, limit: int = 8
    ) -> list[dict[str, Any]]:
        params = {
            "external_chat_id": f"eq.{external_chat_id}",
            "select": "id,direction,message_text,phase_snapshot,intent_snapshot,service_area_snapshot,captured_fields_snapshot,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        return self.fetch_rows("telegram_message_events", params)
