from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings
from app.services.supabase_service import SupabaseService


def normalize_key(value: Any) -> str:
    text = ("" if value is None else str(value)).strip().lower()
    replacements = str.maketrans(
        {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ñ": "n",
        }
    )
    text = text.translate(replacements)
    normalized = []
    previous_space = False
    for char in text:
        if char.isalnum():
            normalized.append(char)
            previous_space = False
        elif not previous_space:
            normalized.append(" ")
            previous_space = True
    return "".join(normalized).strip()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def chunks(items: list[dict[str, Any]], size: int = 100) -> list[list[dict[str, Any]]]:
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def build_event_key(row: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(row.get("sheet_name") or ""),
            str(row.get("clinic_key") or ""),
            str(row.get("clinic_name_raw") or ""),
            str(row.get("patient_name") or ""),
            str(row.get("exam_code") or ""),
            str(row.get("exam_number") or ""),
            str(row.get("pending_exam") or ""),
            str(row.get("status_bucket") or ""),
            str(row.get("reason") or ""),
            str(row.get("registered_flag") or ""),
            str(row.get("observation") or ""),
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync local clients index SQLite into Supabase")
    parser.add_argument(
        "--sqlite",
        default=str(Path(__file__).resolve().parents[1] / ".cache" / "clientes_a3_index.sqlite"),
        help="SQLite index path",
    )
    args = parser.parse_args()

    load_dotenv()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite index not found: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    clinics = [
        row_to_dict(row)
        for row in conn.execute(
            """
            select clinic_key, clinic_name, is_registered, is_new_client, address, locality,
                   phone, email, payment_policy, result_delivery_mode, sources_json
            from clinic_master
            """
        ).fetchall()
    ]
    professionals = [
        row_to_dict(row)
        for row in conn.execute(
            """
            select clinic_key, professional_name, professional_card, source_sheet
            from clinic_professional
            """
        ).fetchall()
    ]
    sample_events = [
        row_to_dict(row)
        for row in conn.execute(
            """
            select sheet_name, clinic_key, clinic_name_raw, patient_name, exam_code, exam_number,
                   pending_exam, status_bucket, reason, registered_flag, observation
            from sample_status_event
            """
        ).fetchall()
    ]

    source_excel = conn.execute("select value from meta where key='source_excel'").fetchone()
    source_excel_value = source_excel[0] if source_excel else ""

    supabase = SupabaseService(
        base_url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key,
    )

    try:
        supabase.fetch_rows("clients_a3_knowledge", {"select": "clinic_key", "limit": "1"})
    except httpx.HTTPStatusError as exc:
        print(
            json.dumps(
                {
                    "error": "Supabase table clients_a3_knowledge not found. Apply SQL migration 006_clients_a3_knowledge_index.sql first.",
                    "status_code": exc.response.status_code,
                },
                ensure_ascii=True,
            )
        )
        return

    clinic_rows = []
    for row in clinics:
        clinic_rows.append(
            {
                "clinic_key": row.get("clinic_key"),
                "clinic_name": row.get("clinic_name"),
                "is_registered": bool(row.get("is_registered")),
                "is_new_client": bool(row.get("is_new_client")),
                "address": row.get("address") or None,
                "locality": row.get("locality") or None,
                "phone": row.get("phone") or None,
                "email": row.get("email") or None,
                "payment_policy": row.get("payment_policy") or None,
                "result_delivery_mode": row.get("result_delivery_mode") or None,
                "sources_json": json.loads(row.get("sources_json") or "[]"),
                "source_excel": source_excel_value or None,
            }
        )

    professional_rows = []
    for row in professionals:
        professional_rows.append(
            {
                "clinic_key": row.get("clinic_key"),
                "professional_key": normalize_key(
                    f"{row.get('professional_name') or ''}|{row.get('professional_card') or ''}"
                ),
                "professional_name": row.get("professional_name") or None,
                "professional_card": row.get("professional_card") or None,
                "source_sheet": row.get("source_sheet") or "unknown",
            }
        )

    sample_rows = []
    for row in sample_events:
        sample_rows.append(
            {
                "event_key": build_event_key(row),
                "source_sheet": row.get("sheet_name") or "unknown",
                "clinic_key": row.get("clinic_key") or None,
                "clinic_name_raw": row.get("clinic_name_raw") or None,
                "patient_name": row.get("patient_name") or None,
                "exam_code": row.get("exam_code") or None,
                "exam_number": row.get("exam_number") or None,
                "pending_exam": row.get("pending_exam") or None,
                "status_bucket": row.get("status_bucket") or "submitted",
                "reason": row.get("reason") or None,
                "registered_flag": row.get("registered_flag") or None,
                "observation": row.get("observation") or None,
            }
        )

    dedup_professionals = {
        (
            row["clinic_key"],
            row["professional_key"],
            row["source_sheet"],
        ): row
        for row in professional_rows
    }
    professional_rows = list(dedup_professionals.values())

    dedup_sample_rows = {row["event_key"]: row for row in sample_rows}
    sample_rows = list(dedup_sample_rows.values())

    for batch in chunks(clinic_rows, size=300):
        supabase.insert_rows(
            "clients_a3_knowledge",
            batch,
            upsert=True,
            on_conflict="clinic_key",
        )

    for batch in chunks(professional_rows, size=300):
        supabase.insert_rows(
            "clients_a3_professionals",
            batch,
            upsert=True,
            on_conflict="clinic_key,professional_key,source_sheet",
        )

    failed_sample_rows = 0
    for batch in chunks(sample_rows, size=100):
        try:
            supabase.insert_rows(
                "clients_a3_sample_events",
                batch,
                upsert=True,
                on_conflict="event_key",
            )
        except httpx.HTTPStatusError:
            for row in batch:
                try:
                    supabase.insert_rows(
                        "clients_a3_sample_events",
                        [row],
                        upsert=True,
                        on_conflict="event_key",
                    )
                except httpx.HTTPStatusError:
                    failed_sample_rows += 1

    result = {
        "sqlite_source": str(sqlite_path),
        "clinics_synced": len(clinic_rows),
        "professionals_synced": len(professional_rows),
        "sample_events_synced": len(sample_rows),
        "sample_events_failed": failed_sample_rows,
    }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
