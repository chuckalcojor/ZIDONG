from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
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
    out = []
    previous_space = False
    for char in text:
        if char.isalnum():
            out.append(char)
            previous_space = False
        elif not previous_space:
            out.append(" ")
            previous_space = True
    return "".join(out).strip()


def like_pattern(value: str) -> str:
    return f"%{normalize_key(value)}%"


def fetch_clinic(conn: sqlite3.Connection, clinic_name: str) -> dict:
    row = conn.execute(
        """
        select
            clinic_key,
            clinic_name,
            is_registered,
            is_new_client,
            address,
            locality,
            phone,
            email,
            payment_policy,
            result_delivery_mode,
            sources_json
        from clinic_master
        where clinic_key like ?
        order by length(clinic_key) asc
        limit 1
        """,
        (like_pattern(clinic_name),),
    ).fetchone()

    if not row:
        return {"found": False, "query": clinic_name}

    professionals = conn.execute(
        """
        select professional_name, professional_card, source_sheet
        from clinic_professional
        where clinic_key = ?
        order by professional_name asc
        """,
        (row["clinic_key"],),
    ).fetchall()

    sample_counts = conn.execute(
        """
        select status_bucket, count(*) as total
        from sample_status_event
        where clinic_key = ?
        group by status_bucket
        """,
        (row["clinic_key"],),
    ).fetchall()

    return {
        "found": True,
        "clinic": dict(row),
        "professionals": [dict(item) for item in professionals],
        "sample_status_summary": {item["status_bucket"]: item["total"] for item in sample_counts},
    }


def fetch_sample_status(conn: sqlite3.Connection, clinic_name: str, patient: str | None) -> dict:
    clinic_key = normalize_key(clinic_name)
    params: list[str] = [f"%{clinic_key}%"]
    where_clause = "where clinic_key like ?"
    if patient:
        where_clause += " and lower(patient_name) like ?"
        params.append(f"%{patient.strip().lower()}%")

    rows = conn.execute(
        f"""
        select
            sheet_name,
            clinic_name_raw,
            patient_name,
            exam_code,
            exam_number,
            pending_exam,
            status_bucket,
            reason,
            registered_flag,
            observation
        from sample_status_event
        {where_clause}
        order by id desc
        limit 20
        """,
        tuple(params),
    ).fetchall()

    summary = conn.execute(
        f"""
        select status_bucket, count(*) as total
        from sample_status_event
        {where_clause}
        group by status_bucket
        """,
        tuple(params),
    ).fetchall()

    return {
        "query": {"clinic_name": clinic_name, "patient": patient or ""},
        "total_rows": len(rows),
        "status_summary": {item["status_bucket"]: item["total"] for item in summary},
        "recent_events": [dict(row) for row in rows],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Query normalized index from Clientes A3 workbook")
    parser.add_argument(
        "--sqlite",
        default=str(Path(__file__).resolve().parents[1] / ".cache" / "clientes_a3_index.sqlite"),
        help="SQLite index path",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["clinic", "sample_status"],
        help="Query mode",
    )
    parser.add_argument("--clinic", required=True, help="Clinic name or partial name")
    parser.add_argument("--patient", help="Optional patient name for sample_status mode")
    args = parser.parse_args()

    conn = sqlite3.connect(args.sqlite)
    conn.row_factory = sqlite3.Row

    if args.mode == "clinic":
        result = fetch_clinic(conn, args.clinic)
    else:
        result = fetch_sample_status(conn, args.clinic, args.patient)

    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
