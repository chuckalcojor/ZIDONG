from __future__ import annotations

import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from dotenv import load_dotenv
from pypdf import PdfReader

from app.config import settings
from app.services.supabase_service import SupabaseService


CODE_LINE = re.compile(r"^\s*(\d{3,4})\s+(.+?)\s+\$\s*([\d\.,]+)\s*$")
ALT_CODE_LINE = re.compile(r"^\s*(\d{3,4})\s+(.+?)\s+([\d\.,]+)\s*\$\s*$")
TURNAROUND_LINE = re.compile(r"Tiempo de entrega:\s*([^\n]+)", re.IGNORECASE)


def normalize_price(value: str) -> int | None:
    clean = value.replace(".", "").replace(",", "").strip()
    if not clean.isdigit():
        return None
    return int(clean)


def parse_turnaround_hours(text: str | None) -> int | None:
    if not text:
        return None
    lowered = text.lower()
    hour_match = re.search(r"(\d+)\s*hor", lowered)
    if hour_match:
        return int(hour_match.group(1))
    day_match = re.search(r"(\d+)\s*d[ií]a", lowered)
    if day_match:
        return int(day_match.group(1)) * 24
    return None


def is_category_line(line: str) -> bool:
    raw = line.strip()
    if not raw:
        return False
    if len(raw) > 70:
        return False
    if any(char.isdigit() for char in raw):
        return False
    return raw.upper() == raw


def main() -> None:
    load_dotenv()
    pdf_path = Path(
        r"C:\Users\Artel\Downloads\LABERIT A3 VETERINARIA\Informacion\A3 - Catalogo 2025 (3) (4).pdf"
    )

    reader = PdfReader(str(pdf_path))
    current_category = "SIN_CATEGORIA"
    current_turnaround: int | None = None
    current_turnaround_text: str | None = None
    tests: list[dict[str, object]] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for line in lines:
            turnaround_match = TURNAROUND_LINE.search(line)
            if turnaround_match:
                turnaround_text = turnaround_match.group(1).strip()
                current_turnaround_text = turnaround_text
                current_turnaround = parse_turnaround_hours(turnaround_text)

            if is_category_line(line):
                current_category = line.strip()

            match = CODE_LINE.match(line) or ALT_CODE_LINE.match(line)
            if not match:
                continue

            code = match.group(1)
            name = match.group(2).strip()
            price = normalize_price(match.group(3))

            tests.append(
                {
                    "test_code": code,
                    "test_name": name,
                    "category": current_category,
                    "subcategory": current_turnaround_text,
                    "sample_type": None,
                    "turnaround_hours": current_turnaround,
                    "price_cop": price,
                    "source": "catalog_pdf",
                    "is_active": True,
                }
            )

    dedup: dict[str, dict[str, object]] = {}
    for item in tests:
        dedup[str(item["test_code"])] = item

    payload = list(dedup.values())

    supabase = SupabaseService(
        base_url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key,
    )
    if payload:
        try:
            supabase.insert_rows(
                "analysis_catalog",
                payload,
                upsert=True,
                on_conflict="test_code",
            )
        except httpx.HTTPStatusError as exc:
            print(
                json.dumps(
                    {
                        "error": "Supabase schema not ready. Run 002_dashboard_operational_schema.sql first.",
                        "status_code": exc.response.status_code,
                    },
                    ensure_ascii=True,
                )
            )
            return

    print(
        json.dumps(
            {
                "tests_extracted": len(tests),
                "tests_upserted": len(payload),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
