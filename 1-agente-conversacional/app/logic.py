from datetime import datetime, timedelta
import re


ROUTES = {
    "programacion de ruta": "route_scheduling",
    "ruta": "route_scheduling",
    "contabilidad": "accounting",
    "resultados": "results",
    "cliente nuevo": "new_client",
}

RESULTS_GREETING_WORDS = {
    "hola",
    "buenas",
    "buenos",
    "dias",
    "tardes",
    "noches",
    "como",
    "estas",
    "vas",
    "gracias",
    "ok",
    "okay",
}

RESULTS_NON_REFERENCE_HINTS = {
    "analizar",
    "analisis",
    "muestra",
    "muestras",
    "mandar",
    "enviar",
    "programar",
    "retiro",
    "ruta",
    "quiero",
    "necesito",
}


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def route_message(message: str) -> dict:
    normalized = normalize(message)
    service_area = ROUTES.get(normalized, "unknown")
    human_handoff = service_area in {"unknown", "accounting"}
    return {
        "service_area": service_area,
        "human_handoff": human_handoff,
        "original_message": message,
        "normalized_message": normalized,
    }


def is_business_day(date_obj) -> bool:
    return date_obj.weekday() < 5


def next_business_day(date_obj):
    candidate = date_obj + timedelta(days=1)
    while not is_business_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def calculate_schedule(received_at_iso: str, cutoff: str = "17:30") -> dict:
    received_at = datetime.fromisoformat(received_at_iso)
    cutoff_hour, cutoff_minute = cutoff.split(":")
    cutoff_time = received_at.replace(
        hour=int(cutoff_hour), minute=int(cutoff_minute), second=0, microsecond=0
    )

    if received_at <= cutoff_time and is_business_day(received_at):
        scheduled_date = next_business_day(received_at).date()
        reason = "next_business_day_before_cutoff"
    else:
        first_business_day = next_business_day(received_at)
        scheduled_date = next_business_day(first_business_day).date()
        reason = "second_business_day_after_cutoff"

    return {
        "received_at": received_at_iso,
        "cutoff": cutoff,
        "scheduled_pickup_date": scheduled_date.isoformat(),
        "reason": reason,
    }


def assign_courier(payload: dict) -> dict:
    request_id = payload.get("request_id")
    client_id = payload.get("client_id")
    assigned_courier_id = payload.get("assigned_courier_id")
    priority = payload.get("priority", "normal")

    if assigned_courier_id:
        return {
            "request_id": request_id,
            "client_id": client_id,
            "assigned": True,
            "status": "assigned",
            "courier_id": assigned_courier_id,
            "priority": priority,
            "fallback_triggered": False,
            "fallback_reason": None,
        }

    return {
        "request_id": request_id,
        "client_id": client_id,
        "assigned": False,
        "status": "error_pending_assignment",
        "courier_id": None,
        "priority": priority,
        "fallback_triggered": True,
        "fallback_reason": "client_without_assigned_courier",
    }


def extract_results_reference(message: str) -> dict[str, str]:
    text = (message or "").strip()
    if not text:
        return {}

    number_match = re.search(r"\b\d{3,}\b", text)
    if number_match:
        return {"sample_reference": number_match.group(0)}

    words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}", text)
    if not words:
        return {}

    lower_words = [word.lower() for word in words]
    if all(word in RESULTS_GREETING_WORDS for word in lower_words):
        return {}

    if any(word in RESULTS_NON_REFERENCE_HINTS for word in lower_words):
        return {}

    candidate = " ".join(words[:2]).strip()
    if not candidate:
        return {}
    return {"pet_name": candidate}


def clear_results_missing_fields(missing_fields: list[str]) -> list[str]:
    cleaned: list[str] = []
    for field in missing_fields:
        lowered = (field or "").lower()
        if "muestra" in lowered or "mascota" in lowered or "orden" in lowered:
            continue
        cleaned.append(field)
    return cleaned
