import unittest

import httpx

from app import main


class FakeSupabaseDashboard:
    def __init__(self) -> None:
        self.update_request_calls: list[tuple[str, dict]] = []
        self.request_events: list[dict] = []
        self.update_rows_calls: list[tuple[str, dict, dict]] = []
        self.insert_rows_calls: list[tuple[str, list[dict]]] = []
        self.locality_coverage_upserts: list[dict] = []
        self.locality_coverage_deletes: list[str] = []
        self.duplicate_courier_phones: set[str] = set()
        self.active_couriers: list[dict] = [
            {
                "id": "courier-1",
                "name": "Juan Motos",
                "phone": "3000000001",
                "availability": "available",
                "is_active": True,
            }
        ]
        self.sample_insert_counter = 0

    def update_request(self, request_id: str, payload: dict) -> None:
        self.update_request_calls.append((request_id, dict(payload)))

    def create_request_event(self, request_id: str, event_type: str, event_payload: dict) -> None:
        self.request_events.append(
            {
                "request_id": request_id,
                "event_type": event_type,
                "event_payload": dict(event_payload),
            }
        )

    def update_rows(self, table: str, filters: dict, payload: dict) -> None:
        if table == "couriers":
            phone = str(payload.get("phone") or "").strip()
            if phone and phone in self.duplicate_courier_phones:
                request = httpx.Request("PATCH", "https://example.supabase.test/rest/v1/couriers")
                response = httpx.Response(
                    409,
                    request=request,
                    text='duplicate key value violates unique constraint "couriers_phone_key"',
                )
                raise httpx.HTTPStatusError("duplicate_courier_phone", request=request, response=response)
        self.update_rows_calls.append((table, dict(filters), dict(payload)))

    def insert_rows(self, table: str, rows: list[dict], upsert: bool = False, on_conflict: str | None = None):
        _ = (upsert, on_conflict)
        copied_rows = [dict(row) for row in rows]
        if table == "lab_samples":
            for row in copied_rows:
                self.sample_insert_counter += 1
                row.setdefault(
                    "id",
                    f"11111111-1111-4111-8111-{self.sample_insert_counter:012d}",
                )
        self.insert_rows_calls.append((table, copied_rows))
        return copied_rows

    def list_active_couriers(self, limit: int = 2000) -> list[dict]:
        return self.active_couriers[:limit]

    def upsert_courier_locality_coverage(
        self,
        *,
        locality_code: str,
        locality_name: str,
        courier_id: str,
        assigned_by: str = "dashboard_manual",
    ) -> None:
        self.locality_coverage_upserts.append(
            {
                "locality_code": locality_code,
                "locality_name": locality_name,
                "courier_id": courier_id,
                "assigned_by": assigned_by,
            }
        )

    def delete_courier_locality_coverage(self, locality_code: str) -> int:
        self.locality_coverage_deletes.append(locality_code)
        return 1


class DashboardManualOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_supabase = main.supabase
        self.fake_supabase = FakeSupabaseDashboard()
        main.supabase = self.fake_supabase
        self.client = main.app.test_client()
        with self.client.session_transaction() as session_state:
            session_state["is_authenticated"] = True
            session_state["username"] = "demo"

    def tearDown(self) -> None:
        main.supabase = self.original_supabase

    def test_request_operation_accepts_high_priority_and_logs_event(self) -> None:
        response = self.client.post(
            "/api/dashboard/request-operation",
            json={
                "request_id": "req-1",
                "priority": "alta",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("priority"), "high")

        self.assertEqual(len(self.fake_supabase.update_request_calls), 1)
        request_id, update_payload = self.fake_supabase.update_request_calls[0]
        self.assertEqual(request_id, "req-1")
        self.assertEqual(update_payload.get("priority"), "urgent")

        self.assertEqual(len(self.fake_supabase.request_events), 1)
        event_payload = self.fake_supabase.request_events[0]["event_payload"]
        self.assertEqual(event_payload.get("priority"), "high")
        self.assertEqual(event_payload.get("priority_db_value"), "urgent")

    def test_request_operation_updates_sample_count_and_sample_types(self) -> None:
        response = self.client.post(
            "/api/dashboard/request-operation",
            json={
                "request_id": "req-2",
                "sample_count": "3",
                "sample_types": ["Sangre", "Orina", "Sangre"],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("sample_count"), 3)
        self.assertEqual(body.get("sample_types"), ["Sangre", "Orina"])

        self.assertEqual(len(self.fake_supabase.request_events), 1)
        event_payload = self.fake_supabase.request_events[0]["event_payload"]
        self.assertEqual(event_payload.get("sample_count"), 3)
        self.assertEqual(event_payload.get("sample_types"), ["Sangre", "Orina"])

    def test_sample_status_processed_uses_event_only_mode(self) -> None:
        response = self.client.post(
            "/api/dashboard/sample-status",
            json={
                "sample_id": "sample-1",
                "status": "processed",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("persistence_mode"), "event_only")

        self.assertEqual(self.fake_supabase.update_rows_calls, [])
        self.assertEqual(len(self.fake_supabase.insert_rows_calls), 1)
        table_name, rows = self.fake_supabase.insert_rows_calls[0]
        self.assertEqual(table_name, "lab_sample_events")
        self.assertEqual(rows[0].get("event_payload", {}).get("status"), "processed")

    def test_sample_status_pending_pickup_updates_lab_samples(self) -> None:
        response = self.client.post(
            "/api/dashboard/sample-status",
            json={
                "sample_id": "sample-2",
                "status": "pending_pickup",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("persistence_mode"), "lab_samples_and_event")

        self.assertEqual(len(self.fake_supabase.update_rows_calls), 1)
        table_name, _filters, payload = self.fake_supabase.update_rows_calls[0]
        self.assertEqual(table_name, "lab_samples")
        self.assertEqual(payload.get("status"), "pending_pickup")

    def test_sample_status_without_id_creates_sample_from_seed(self) -> None:
        response = self.client.post(
            "/api/dashboard/sample-status",
            json={
                "status": "in_lab",
                "sample_seed": {
                    "seed_token": "request:req-1",
                    "sample_type": "Sangre",
                    "test_name": "Pendiente por definir",
                    "priority": "high",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("created_from_seed"))
        self.assertEqual(body.get("persistence_mode"), "created_lab_sample_fallback_and_event")
        self.assertTrue(body.get("sample_id"))

        self.assertEqual(len(self.fake_supabase.update_rows_calls), 0)
        self.assertEqual(len(self.fake_supabase.insert_rows_calls), 2)
        first_table, first_rows = self.fake_supabase.insert_rows_calls[0]
        self.assertEqual(first_table, "lab_samples")
        self.assertEqual(first_rows[0].get("status"), "in_analysis")
        self.assertEqual(first_rows[0].get("priority"), "urgent")

    def test_locality_assignment_updates_coverage(self) -> None:
        response = self.client.post(
            "/api/dashboard/courier-locality-assignment",
            json={
                "locality_code": "kennedy",
                "courier_id": "courier-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("locality_code"), "kennedy")
        self.assertEqual(body.get("courier_id"), "courier-1")

        self.assertEqual(len(self.fake_supabase.locality_coverage_upserts), 1)
        upsert_payload = self.fake_supabase.locality_coverage_upserts[0]
        self.assertEqual(upsert_payload.get("locality_name"), "Kennedy")

    def test_locality_assignment_without_courier_clears_coverage(self) -> None:
        response = self.client.post(
            "/api/dashboard/courier-locality-assignment",
            json={
                "locality_code": "suba",
                "courier_id": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertIsNone(body.get("courier_id"))
        self.assertEqual(self.fake_supabase.locality_coverage_deletes, ["suba"])

    def test_courier_phone_update_persists_value(self) -> None:
        response = self.client.post(
            "/api/dashboard/courier-phone",
            json={
                "courier_id": "courier-1",
                "phone": " 300 123 4567 ",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("courier_id"), "courier-1")
        self.assertEqual(body.get("phone"), "3001234567")

        self.assertEqual(len(self.fake_supabase.update_rows_calls), 1)
        table_name, filters, payload = self.fake_supabase.update_rows_calls[0]
        self.assertEqual(table_name, "couriers")
        self.assertEqual(filters.get("id"), "eq.courier-1")
        self.assertEqual(payload.get("phone"), "3001234567")

    def test_courier_phone_update_rejects_duplicate_phone(self) -> None:
        self.fake_supabase.duplicate_courier_phones.add("3005550000")

        response = self.client.post(
            "/api/dashboard/courier-phone",
            json={
                "courier_id": "courier-1",
                "phone": "3005550000",
            },
        )

        self.assertEqual(response.status_code, 409)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertIn("already exists", str(body.get("error") or ""))

    def test_courier_phone_update_rejects_invalid_phone(self) -> None:
        response = self.client.post(
            "/api/dashboard/courier-phone",
            json={
                "courier_id": "courier-1",
                "phone": "abc",
            },
        )

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        assert isinstance(body, dict)
        self.assertEqual(body.get("error"), "Invalid phone")


if __name__ == "__main__":
    unittest.main()
