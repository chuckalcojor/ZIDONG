from __future__ import annotations

import re
import json
import hashlib
from collections import Counter
from datetime import datetime
from functools import wraps
from typing import Any

import httpx
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.config import settings
from app.ai_prompt import SYSTEM_PROMPT
from app.logic import (
    assign_courier,
    calculate_schedule,
    clear_results_missing_fields,
    extract_results_reference,
    route_message,
)
from app.services.openai_service import OpenAIService
from app.services.supabase_service import SupabaseService
from app.services.telegram_service import TelegramService

app = Flask(__name__)
app.secret_key = settings.flask_secret_key
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True

supabase = SupabaseService(
    base_url=settings.supabase_url,
    service_role_key=settings.supabase_service_role_key,
)
telegram = TelegramService(bot_token=settings.telegram_bot_token)
openai_service = (
    OpenAIService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        fallback_model=settings.openai_fallback_model,
        enable_fallback=settings.openai_enable_fallback,
    )
    if settings.openai_api_key
    else None
)

FLOW_STAGES: list[tuple[str, str]] = [
    ("fase_0_bienvenida", "Bienvenida"),
    ("fase_1_clasificacion", "Clasificacion"),
    ("fase_2_recogida_datos", "Recogida de datos"),
    ("fase_3_validacion", "Validacion"),
    ("fase_4_confirmacion", "Confirmacion"),
    ("fase_5_ejecucion", "Ejecucion"),
    ("fase_6_cierre", "Cierre"),
    ("fase_7_escalado", "Escalado humano"),
]
FLOW_STAGE_LABELS = {key: label for key, label in FLOW_STAGES}
FLOW_STAGE_ORDER = {key: idx for idx, (key, _label) in enumerate(FLOW_STAGES)}
VALID_INTENTS = {
    "programacion_rutas",
    "contabilidad",
    "resultados",
    "alta_cliente",
    "no_clasificado",
}
VALID_MESSAGE_MODES = {
    "flow_progress",
    "side_question",
    "intent_switch",
    "small_talk",
}
VALID_NEXT_ACTIONS = {
    "continuar_conversacion",
    "solicitar_clasificacion",
    "solicitar_nif_o_nombre_fiscal",
    "solicitar_cliente_y_direccion",
    "confirmar_direccion_retiro",
    "solicitar_direccion_actualizada",
    "confirmar_programacion_ruta",
    "compartir_formulario_registro_cliente",
    "share_pqrs_link",
    "atender_otra_consulta",
}
EXPLICIT_INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "route_scheduling": (
        "programacion de ruta",
        "programar ruta",
        "programar recogida",
        "programar recoleccion",
        "agendar retiro",
        "agendar recogida",
        "programar retiro",
        "programar un retiro",
        "quiero mandar a analizar una muestra",
        "mandar a analizar una muestra",
        "mandar a analizar muestras",
        "analizar una muestra",
        "analizar muestras",
        "analizar muestra",
        "quiero analizar una muestra",
        "quiero analizar muestras",
        "enviar muestra",
        "enviar muestras",
        "enviar prueba",
        "enviar pruebas",
        "enviar examen",
        "enviar examenes",
        "mandar una prueba a analizar",
        "mandar prueba a analizar",
        "mandar examen a analizar",
        "procesar muestra",
        "procesar prueba",
        "procesar examen",
        "procesar analitica",
        "tomar muestra",
        "toma de muestra",
        "recoleccion de muestra",
        "recolectar muestra",
        "recolectar pruebas",
        "recolectar examenes",
        "muestra biologica",
        "muestra clinica",
        "remitir muestra",
        "remision de muestra",
        "envio al laboratorio",
        "domicilio para recoger",
        "domicilio para retiro",
        "recoger muestra",
        "retiro de muestra",
        "retirar muestra",
        "retiro",
        "ruta",
    ),
    "results": (
        "resultado",
        "resultados",
        "consulta de resultados",
        "consultar resultados",
        "estado de resultado",
        "estado de la muestra",
        "me compartes el diagnostico",
        "compartes el diagnostico",
        "informe",
        "reporte",
        "dictamen",
        "lectura",
        "seguimiento",
        "trazabilidad",
        "estado del caso",
        "estado de orden",
        "cerraron el estudio",
        "publicado el analisis",
    ),
    "accounting": (
        "contabilidad",
        "factura",
        "facturacion",
        "cartera",
        "pago",
        "pagos",
        "cobro",
        "deuda",
        "financiera",
        "abono",
        "saldo",
        "estado de cuenta",
        "cierre contable",
        "conciliar",
        "diferencia en valores",
        "cargo en mi cuenta",
        "monto",
    ),
    "new_client": (
        "cliente nuevo",
        "registrarme",
        "registrame",
        "registrar",
        "registrarse",
        "registrar cliente",
        "registro",
        "darse de alta",
        "darme de alta",
        "no estoy registrado",
        "no estoy registrada",
        "no estoy en la base",
        "primera vez",
        "vincular mi veterinaria",
        "vincular mi clinica",
    ),
}
SMALL_TALK_TOKENS = {
    "hola",
    "holaa",
    "holaaa",
    "buenas",
    "gracias",
    "ok",
    "okay",
    "como estas",
    "como estas?",
    "como va",
    "como vas",
    "bien",
    "si",
    "sii",
    "dale",
}
AFFIRMATIVE_TOKENS = {"si", "s", "claro", "correcto", "de acuerdo", "confirmo", "ok", "okay"}
NEGATIVE_TOKENS = {"no", "negativo", "incorrecto", "cambiar", "no aplica"}
INITIAL_GREETING_MESSAGE = (
    "Hola! Buen día, me alegra que nos visites.\n"
    "Bienvenido a A3 laboratorio clínico veterinario 🧪 🧫\n"
    "¿En qué podemos ayudarte?"
)
INITIAL_GREETING_MESSAGE_NO_QUESTION = (
    "Hola! Buen día, me alegra que nos visites.\n"
    "Bienvenido a A3 laboratorio clínico veterinario 🧪 🧫"
)
INTENT_CLARIFICATION_MESSAGE = (
    "Para ayudarte mejor, cuéntame qué necesitas hoy:\n"
    " 1. Programar recogida de muestras\n"
    " 2. Consulta de resultados\n"
    " 3. Aclara tus pagos\n"
    " 4. ¿Eres cliente nuevo?\n"
    " 5. PQRS\n"
    " 6. Otras consultas"
)
PQRS_LINK_URL = "https://a3laboratorio.co/pqrs/"
PQRS_MESSAGE = (
    "Claro, para PQRS te invitamos a diligenciar el siguiente enlace: "
    f"{PQRS_LINK_URL}"
)
OTHER_QUERIES_MESSAGE = (
    "Perfecto, te ayudo con otras consultas. "
    "Cuéntame tu pregunta con el mayor detalle posible y te orientaré de inmediato."
)
ROUTE_REMINDER_MESSAGE = (
    "Recordatorio: si ya cuentas con el formulario de remision de domicilios en fisico, "
    "puedes usarlo y entregarlo al motorizado al momento del retiro. "
    "Si no lo tienes, puedes generarlo e imprimirlo aqui: "
    "https://docs.google.com/forms/d/e/1FAIpQLSd2xEe2utpAefWOCf5Zc7QJHsGfB-DgupJoyQpG8oaFeTofFA/viewform. "
    "Para procesar la muestra, debe diligenciarse completo antes de las 5:30 PM; "
    "despues de esa hora se procesa al siguiente dia habil."
)
NEW_CLIENT_REGISTRATION_FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLScwimzCqx01C_6yMEn8caTgNWgXZ2rEYbwsFnJKM4e6ckLzLg/viewform"
)
NEW_CLIENT_REGISTRATION_MESSAGE = (
    "Perfecto, te ayudo con el registro como cliente nuevo. "
    "Para completar el alta, por favor diligencia este formulario: "
    f"{NEW_CLIENT_REGISTRATION_FORM_URL} "
    "Es un registro sencillo y lo haces directamente alli, "
    "asi ya quedas registrado en nuestra base de datos. "
    "Cuando lo completes, te acompanamos con la programacion de ruta o con lo que necesites."
)
NEW_CLIENT_POST_REGISTRATION_MESSAGE = (
    "Genial, si ya estas registrado podemos proceder con la programacion de ruta o con lo que necesites. "
    "¿Deseas programar recogida de muestras, consulta de resultados, aclarar tus pagos, "
    "consultar PQRS u otras consultas?"
)
NEW_CLIENT_POST_REGISTRATION_ROUTE_MESSAGE = (
    "Genial, retomemos la programacion de ruta que solicitaste. "
    "Para continuar, comparteme tu NIF o el nombre fiscal de la veterinaria para ubicar tu registro."
)
ROUTE_CLIENT_IDENTIFICATION_MESSAGE = (
    "Perfecto, te ayudo con eso. "
    "Primero necesito confirmar si ya estas registrado. "
    "Comparteme tu NIF o dime el nombre de la veterinaria para ubicar tu registro. "
    "Si aun no estas registrado, te ayudo a hacerlo ahora."
)


def flow_stage_label(stage_key: str | None) -> str:
    if not stage_key:
        return "Sin etapa"
    return FLOW_STAGE_LABELS.get(stage_key, stage_key.replace("_", " ").title())


def normalize_text_value(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def normalize_lookup_key(text: str) -> str:
    base = normalize_text_value(text)
    if not base:
        return ""
    translated = base.translate(
        str.maketrans(
            {
                "á": "a",
                "é": "e",
                "í": "i",
                "ó": "o",
                "ú": "u",
                "ñ": "n",
            }
        )
    )
    translated = re.sub(r"[^a-z0-9 ]", " ", translated)
    return re.sub(r"\s+", " ", translated).strip()


def normalize_intent_token(token: str) -> str:
    lowered = (token or "").strip().lower()
    if not lowered:
        return ""

    replacements = str.maketrans(
        {
            "a": "a",
            "e": "e",
            "i": "i",
            "o": "o",
            "u": "u",
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ñ": "n",
        }
    )
    normalized = lowered.translate(replacements)
    normalized = re.sub(r"[^a-z0-9]", "", normalized)
    if len(normalized) > 4 and normalized.endswith("es"):
        normalized = normalized[:-2]
    elif len(normalized) > 3 and normalized.endswith("s"):
        normalized = normalized[:-1]
    return normalized


def normalize_next_action_token(
    next_action: str | None,
    *,
    service_area: str,
    status: str,
) -> str:
    candidate = (next_action or "").strip()
    if candidate in VALID_NEXT_ACTIONS:
        return candidate

    normalized = normalize_lookup_key(candidate)
    if not normalized:
        if service_area == "new_client":
            return "compartir_formulario_registro_cliente"
        if service_area == "unknown":
            return "atender_otra_consulta"
        return "continuar_conversacion"

    if "pqrs" in normalized:
        return "share_pqrs_link"
    if "otra consulta" in normalized or "consulta general" in normalized:
        return "atender_otra_consulta"
    if "clasificacion" in normalized:
        return "solicitar_clasificacion"
    if "nif" in normalized or "nit" in normalized or "nombre fiscal" in normalized:
        return "solicitar_nif_o_nombre_fiscal"
    if "cliente" in normalized and "direccion" in normalized:
        return "solicitar_cliente_y_direccion"
    if "direccion" in normalized and "confirm" in normalized:
        return "confirmar_direccion_retiro"
    if "direccion" in normalized and ("actual" in normalized or "nueva" in normalized):
        return "solicitar_direccion_actualizada"
    if "program" in normalized and "confirm" in normalized:
        return "confirmar_programacion_ruta"
    if "registro" in normalized and "cliente" in normalized:
        return "compartir_formulario_registro_cliente"
    if "continu" in normalized:
        return "continuar_conversacion"

    if service_area == "route_scheduling":
        if status in {"confirmed", "closed"}:
            return "continuar_conversacion"
        return "solicitar_cliente_y_direccion"
    if service_area == "new_client":
        return "compartir_formulario_registro_cliente"
    if service_area == "unknown":
        return "atender_otra_consulta"
    return "continuar_conversacion"


def extract_intent_tokens(text: str) -> set[str]:
    normalized = normalize_text_value(text)
    raw_tokens = re.findall(r"[a-zA-Z0-9ÁÉÍÓÚáéíóúÑñ]+", normalized)
    tokens = {normalize_intent_token(token) for token in raw_tokens}
    return {token for token in tokens if token}


def detect_explicit_service_area(text: str) -> str | None:
    normalized = normalize_text_value(text)
    if not normalized:
        return None

    for service_area, patterns in EXPLICIT_INTENT_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return service_area

    tokens = extract_intent_tokens(normalized)
    if not tokens:
        return None

    results_tokens = {
        "resultado",
        "estad",
        "informe",
        "report",
        "diagnost",
        "entrega",
        "list",
        "seguimiento",
        "trazabilidad",
        "dictamen",
        "lectura",
        "orden",
        "estudio",
        "analisi",
        "procesamiento",
        "caso",
        "publicado",
        "salida",
    }
    accounting_tokens = {
        "contabilidad",
        "factura",
        "facturacion",
        "cartera",
        "pago",
        "cobro",
        "cobrad",
        "financiero",
        "deuda",
        "abono",
        "saldo",
        "cuenta",
        "corte",
        "conciliar",
        "diferencia",
        "monto",
        "valor",
    }
    new_client_tokens = {
        "registro",
        "registrar",
        "cliente",
        "nuevo",
        "primer",
        "vez",
        "alta",
        "vincul",
        "afiliar",
        "onboarding",
        "formalizar",
        "ingreso",
        "ingresar",
        "iniciar",
        "habilitar",
        "historial",
        "aliado",
        "trabajar",
        "base",
        "primeravez",
    }
    route_direct_tokens = {
        "ruta",
        "retiro",
        "retirar",
        "recoger",
        "recogida",
        "recoleccion",
        "domicilio",
        "motorizado",
        "mensajero",
        "pickup",
        "logistica",
        "tubo",
        "tubos",
        "material",
        "biologico",
    }
    route_action_tokens = {
        "mandar",
        "enviar",
        "analizar",
        "programar",
        "agendar",
        "retiro",
        "retirar",
        "recoger",
        "recolectar",
        "remitir",
        "coordinar",
        "procesar",
        "tramitar",
        "despachar",
        "tomar",
        "mover",
        "pasar",
        "gestionar",
        "remitir",
        "activar",
    }
    sample_tokens = {
        "muestra",
        "muestr",
        "analisi",
        "prueba",
        "prueb",
        "examen",
        "exam",
        "panel",
        "perfil",
        "serologia",
        "hematologia",
        "coprologia",
        "uroanalisi",
        "citologia",
        "biopsia",
        "hispatologia",
        "molecular",
        "pcr",
    }

    has_results_signal = bool(tokens & results_tokens)
    has_accounting_signal = bool(tokens & accounting_tokens)
    has_new_client_signal = bool(tokens & new_client_tokens)
    has_route_direct_signal = bool(tokens & route_direct_tokens)
    has_route_action_signal = bool(tokens & route_action_tokens)
    has_sample_signal = bool(tokens & sample_tokens)

    scores = {
        "route_scheduling": 0,
        "results": 0,
        "accounting": 0,
        "new_client": 0,
    }

    if has_route_direct_signal:
        scores["route_scheduling"] += 4
    if has_route_action_signal:
        scores["route_scheduling"] += 2
    if has_sample_signal and (has_route_action_signal or has_route_direct_signal):
        scores["route_scheduling"] += 2
    if has_sample_signal and has_route_action_signal:
        scores["route_scheduling"] += 3

    if has_results_signal:
        scores["results"] += 4
    if has_results_signal and has_sample_signal and not has_route_direct_signal:
        scores["results"] += 2
    if has_accounting_signal:
        scores["accounting"] += 4
    if has_new_client_signal:
        scores["new_client"] += 4

    if has_new_client_signal and has_route_action_signal:
        scores["route_scheduling"] += 2
        scores["new_client"] -= 1
    if has_results_signal and has_route_action_signal and has_sample_signal:
        scores["route_scheduling"] += 2
    if has_results_signal and not has_route_action_signal and not has_route_direct_signal:
        scores["route_scheduling"] -= 2
    if has_new_client_signal and not has_route_direct_signal:
        scores["route_scheduling"] -= 2

    ranking = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_area, best_score = ranking[0]
    if best_score <= 0:
        return None

    sorted_scores = sorted(scores.values(), reverse=True)
    score_gap = sorted_scores[0] - sorted_scores[1]
    if best_score >= 4 or score_gap >= 2:
        return best_area

    return None


def detect_semantic_service_area_hint(text: str) -> str | None:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return None

    if is_greeting_only(text) or is_small_talk_only(text):
        return None

    semantic_keywords: dict[str, tuple[str, ...]] = {
        "results": (
            "seguimiento",
            "trazabilidad",
            "dictamen",
            "lectura",
            "avance del procesamiento",
            "estado del caso",
            "salida del informe",
            "cerraron el estudio",
            "publicado el analisis",
        ),
        "new_client": (
            "onboarding",
            "formalizar mi ingreso",
            "nunca he usado",
            "primera vez",
            "vincularme",
            "dar de alta mi negocio",
            "empezar a trabajar con ustedes",
            "nuevo aliado",
            "quiero iniciar",
            "base de clientes",
        ),
        "accounting": (
            "conciliar pagos",
            "cuadrar",
            "cierre contable",
            "montos",
            "cargo en mi cuenta",
        ),
        "route_scheduling": (
            "recogida",
            "retiro",
            "despacho",
            "motorizado",
            "muestras urgentes",
            "logistica",
            "pasen por",
        ),
    }
    semantic_scores: dict[str, int] = {
        area: sum(1 for pattern in patterns if pattern in normalized)
        for area, patterns in semantic_keywords.items()
    }
    ranked_semantic = sorted(semantic_scores.items(), key=lambda item: item[1], reverse=True)
    top_area, top_score = ranked_semantic[0]
    second_score = ranked_semantic[1][1]
    if top_score >= 2 or (top_score >= 1 and top_score > second_score):
        return top_area

    classify_fn = getattr(openai_service, "classify_service_area", None)
    if not callable(classify_fn):
        return None

    try:
        detected = classify_fn(user_message=text)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(detected, str):
        return None

    valid_areas = {"route_scheduling", "results", "accounting", "new_client"}
    if detected in valid_areas:
        return str(detected)
    return None


def detect_numeric_menu_option(text: str) -> str | None:
    normalized = normalize_text_value(text)
    if not normalized:
        return None

    match = re.fullmatch(r"([1-6])[\).]?", normalized)
    if not match:
        return None

    return {
        "1": "route_scheduling",
        "2": "results",
        "3": "accounting",
        "4": "new_client",
        "5": "pqrs",
        "6": "other_queries",
    }.get(match.group(1))


def detect_special_menu_option(text: str) -> str | None:
    numeric_option = detect_numeric_menu_option(text)
    if numeric_option in {"pqrs", "other_queries"}:
        return numeric_option

    normalized = normalize_text_value(text)
    if not normalized:
        return None

    if "pqrs" in normalized:
        return "pqrs"

    pqrs_patterns = (
        "queja",
        "reclamo",
        "peticion",
        "sugerencia",
        "felicitacion",
        "radicar",
    )
    if any(pattern in normalized for pattern in pqrs_patterns):
        return "pqrs"

    other_queries_patterns = (
        "otras consultas",
        "otra consulta",
        "consulta general",
        "consulta adicional",
        "consulta distinta",
        "consulta no relacionada",
        "otra duda",
        "otra inquietud",
        "otra pregunta",
        "pregunta adicional",
        "pregunta general",
        "duda general",
        "ayuda con informacion",
        "quiero hacer una consulta",
        "me ayudas con otra consulta",
        "soporte general",
        "orientacion general",
        "informacion general",
    )
    if any(pattern in normalized for pattern in other_queries_patterns):
        return "other_queries"

    return None


def is_small_talk_only(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return True
    return normalized in SMALL_TALK_TOKENS


def is_greeting_only(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    words = re.findall(r"[a-zA-Z]+", normalized)
    if not words:
        return False

    greeting_words = {
        "hola",
        "buen",
        "buena",
        "buenas",
        "buenos",
        "dias",
        "tardes",
        "noches",
        "hey",
        "holi",
        "como",
        "estas",
        "estan",
        "tal",
        "que",
    }
    return all(word in greeting_words for word in words)


def is_wellbeing_greeting(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    wellbeing_patterns = (
        "hola como estas",
        "hola como estan",
        "como estas",
        "como estan",
        "que tal",
        "como va",
        "como vas",
        "como se encuentran",
        "todo bien",
    )
    return any(pattern in normalized for pattern in wellbeing_patterns)


def is_affirmative_reply(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False
    if normalized in AFFIRMATIVE_TOKENS:
        return True

    words = normalized.split()
    if not words:
        return False

    if words[0] in {"si", "s", "ok", "okay", "claro", "confirmo"}:
        return True

    if "de acuerdo" in normalized:
        return True

    if re.search(r"\bconfirmo\b", normalized):
        return True

    if re.search(r"\bcorrecto\b", normalized):
        return True

    if any(token in normalized for token in ("ya lo tengo", "ya la tengo", "ya tienen mi direccion")):
        return True

    return False


def is_negative_reply(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False
    if normalized in NEGATIVE_TOKENS:
        return True

    words = normalized.split()
    if not words:
        return False

    if words[0] == "no":
        return True

    return any(token in normalized for token in ("cambiar", "cambia", "incorrect", "ajustar"))


def is_help_inquiry(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    help_tokens = (
        "en que puedes ayudar",
        "en que me puedes ayudar",
        "en que me ayudas",
        "en que puede ayudar",
        "en que puede ayudarme",
        "en que ayudan",
        "que puedes hacer",
        "que servicios",
        "como me ayudas",
    )
    return any(token in normalized for token in help_tokens)


def is_price_or_services_inquiry(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    tokens = (
        "cuanto",
        "precio",
        "precios",
        "costos",
        "costo",
        "tarifa",
        "tarifas",
        "que puedo hacer",
        "que servicios",
        "servicios tienen",
    )
    return any(token in normalized for token in tokens)


def should_split_first_greeting(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    has_greeting = any(token in normalized for token in ("hola", "buen", "buenas", "como estas", "que tal"))
    return has_greeting and is_help_inquiry(text)


def parse_clinic_and_address_from_text(text: str) -> tuple[str | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return None, None

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) >= 2:
        clinic_candidate = parts[0]
        address_candidate = ", ".join(parts[1:])
        return clinic_candidate or None, address_candidate or None

    has_digit = any(char.isdigit() for char in raw)
    if has_digit:
        return None, raw

    return raw, None

def extract_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d{10,15})", text)
    if not match:
        return None
    return match.group(1)


def normalize_tax_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (value or "").upper())


def extract_tax_id_candidate(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    tagged = re.search(
        r"(?:nif|nit|rut|rif)(?:\s+es)?\s*[:#-]?\s*([A-Za-z0-9.-]{5,20})",
        raw,
        flags=re.IGNORECASE,
    )
    if tagged:
        candidate = normalize_tax_id(tagged.group(1))
        return candidate if len(candidate) >= 5 else None

    if re.fullmatch(r"[A-Za-z0-9.-]{6,20}", raw):
        candidate = normalize_tax_id(raw)
        return candidate if len(candidate) >= 5 else None

    return None


def user_declares_not_registered(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    tokens = (
        "no estoy registrado",
        "no estoy registrada",
        "aun no estoy registrado",
        "no estoy en la base",
        "soy cliente nuevo",
        "es primera vez",
        "primera vez",
    )
    return any(token in normalized for token in tokens)


def user_confirms_registration_completed(text: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    completion_tokens = (
        "ya me registre",
        "ya me registré",
        "listo ya me registre",
        "listo ya me registré",
        "ya estoy registrado",
        "ya estoy registrada",
        "ya complete el formulario",
        "ya completé el formulario",
        "ya lo complete",
        "ya lo completé",
        "lo complete",
        "lo completé",
        "ya diligencie el formulario",
        "ya diligencié el formulario",
        "ya llene el formulario",
        "ya llené el formulario",
        "formulario listo",
        "registro listo",
    )
    if any(token in normalized for token in completion_tokens):
        return True

    has_completed_signal = any(
        token in normalized
        for token in ("complet", "diligenc", "llen", "registre", "registr")
    )
    has_done_prefix = normalized.startswith("ya") or "listo" in normalized
    return has_completed_signal and has_done_prefix


def get_pending_post_registration_target(captured_fields: dict[str, Any]) -> tuple[str | None, str | None]:
    if not isinstance(captured_fields, dict):
        return None, None

    pending_service_area = normalize_text_value(
        str(captured_fields.get("post_registration_service_area") or "")
    )
    pending_intent = normalize_text_value(str(captured_fields.get("post_registration_intent") or ""))

    valid_service_areas = {"route_scheduling", "accounting", "results", "new_client"}
    valid_intents = {"programacion_rutas", "contabilidad", "resultados", "alta_cliente"}

    if pending_service_area not in valid_service_areas:
        pending_service_area = None
    if pending_intent not in valid_intents:
        pending_intent = None

    return pending_service_area, pending_intent


def clear_post_registration_target(captured_fields: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(captured_fields, dict):
        return {}

    cleaned = dict(captured_fields)
    cleaned.pop("post_registration_service_area", None)
    cleaned.pop("post_registration_intent", None)
    return cleaned


def extract_clinic_name_hint(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    hint = raw
    anchored_match_found = False

    anchored_patterns = (
        r"^\s*(?:si\s+)?(?:estoy\s+)?(?:registrad[oa]\s*,?\s*)?(.+?)\s+es\s+la\s+veterinaria\s*$",
        r"^\s*(.+?)\s+es\s+el\s+nombre(?:\s+fiscal)?\s*$",
        r"^\s*(.+?)\s+es\s+mi\s+veterinaria\s*$",
    )
    for pattern in anchored_patterns:
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            candidate = (match.group(1) or "").strip(" :,-")
            if len(candidate) >= 4:
                hint = candidate
                anchored_match_found = True
                break
    prefixes = (
        "mi nombre de veterinaria es",
        "nombre de veterinaria",
        "mi veterinaria es",
        "la veterinaria es",
        "nombre fiscal",
        "nombre de la veterinaria",
        "veterinaria",
        "clinica",
    )
    if not anchored_match_found:
        lowered = raw.lower()
        for prefix in prefixes:
            idx = lowered.find(prefix)
            if idx >= 0:
                hint = raw[idx + len(prefix) :].strip(" :,-")
                break

    hint = re.sub(r"^es\s+", "", hint, flags=re.IGNORECASE).strip()
    hint = re.sub(
        r"^(?:si\s+)?(?:estoy\s+)?(?:registrad[oa])\s*,?\s*",
        "",
        hint,
        flags=re.IGNORECASE,
    ).strip()
    hint = re.sub(r"\s+es\s+la\s+veterinaria$", "", hint, flags=re.IGNORECASE).strip()
    hint = re.sub(r"\s+es\s+el\s+nombre(?:\s+fiscal)?$", "", hint, flags=re.IGNORECASE).strip()

    for separator in (" y ", ",", "."):
        if separator in hint.lower():
            hint = hint.split(separator, 1)[0].strip()
            break

    if len(hint) < 4:
        return None
    return hint


def extract_form_value(payload: dict[str, Any], aliases: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ""

    normalized_items = []
    for key, value in payload.items():
        normalized_key = normalize_lookup_key(str(key))
        if not normalized_key:
            continue
        normalized_items.append((normalized_key, value))

    normalized_aliases = [normalize_lookup_key(alias) for alias in aliases if normalize_lookup_key(alias)]

    for alias in normalized_aliases:
        for key, value in normalized_items:
            if key == alias:
                return ("" if value is None else str(value)).strip()

    for alias in normalized_aliases:
        for key, value in normalized_items:
            if alias in key:
                return ("" if value is None else str(value)).strip()

    return ""


def ensure_dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def identify_client_by_tax_id_or_clinic(incoming_text: str) -> dict[str, Any] | None:
    tax_id = extract_tax_id_candidate(incoming_text)
    if tax_id:
        try:
            client = supabase.get_client_by_tax_id(tax_id)
            if client:
                return client
        except httpx.HTTPStatusError:
            return None

    clinic_hint = extract_clinic_name_hint(incoming_text)
    if clinic_hint:
        try:
            matches = supabase.search_clients_by_clinic_name(clinic_hint, limit=3)
        except httpx.HTTPStatusError:
            return None
        if len(matches) == 1:
            client_match = dict(matches[0])
            if not is_meaningful_value(client_match.get("address")):
                search_a3_knowledge = getattr(supabase, "search_a3_knowledge_by_clinic_name", None)
                if callable(search_a3_knowledge):
                    try:
                        knowledge_rows = ensure_dict_rows(search_a3_knowledge(clinic_hint, limit=1))
                    except httpx.HTTPStatusError:
                        knowledge_rows = []
                    if knowledge_rows:
                        client_match["address"] = knowledge_rows[0].get("address")
            return client_match

        search_a3_knowledge = getattr(supabase, "search_a3_knowledge_by_clinic_name", None)
        if callable(search_a3_knowledge):
            try:
                raw_matches = search_a3_knowledge(clinic_hint, limit=3)
            except httpx.HTTPStatusError:
                raw_matches = []

            knowledge_matches = ensure_dict_rows(raw_matches)

            if knowledge_matches:
                best = knowledge_matches[0]
                return {
                    "id": None,
                    "clinic_name": best.get("clinic_name"),
                    "phone": best.get("phone"),
                    "tax_id": None,
                    "address": best.get("address"),
                    "clinic_key": best.get("clinic_key"),
                    "is_registered": bool(best.get("is_registered", False)),
                    "is_new_client": bool(best.get("is_new_client", False)),
                }

    return None


def summarize_a3_sample_status(clinic_key: str) -> dict[str, Any] | None:
    if not clinic_key:
        return None

    fetch_events = getattr(supabase, "list_a3_sample_events", None)
    if not callable(fetch_events):
        return None

    try:
        raw_rows = fetch_events(clinic_key, limit=250)
    except httpx.HTTPStatusError:
        return None

    rows = ensure_dict_rows(raw_rows)

    if not rows:
        return None

    status_counter = Counter((row.get("status_bucket") or "unknown") for row in rows)
    reason_counter = Counter((row.get("reason") or "").strip() for row in rows if row.get("reason"))
    top_reason = reason_counter.most_common(1)[0][0] if reason_counter else ""

    return {
        "submitted": status_counter.get("submitted", 0),
        "pending_issue": status_counter.get("pending_issue", 0),
        "top_reason": top_reason,
    }


def build_route_mock_idempotency_key(
    *,
    chat_id: int,
    clinic_name: str,
    pickup_address: str,
    scheduled_pickup_date: str | None,
) -> str:
    seed = "|".join(
        [
            str(chat_id),
            normalize_lookup_key(clinic_name),
            normalize_lookup_key(pickup_address),
            str(scheduled_pickup_date or ""),
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def submit_route_mock_record(
    *,
    chat_id: int,
    request_id: str,
    client_id: str | None,
    captured_fields: dict[str, Any],
    scheduled_pickup_date: str | None,
) -> dict[str, Any]:
    clinic_name = str(captured_fields.get("clinic_name") or "").strip()
    pickup_address = str(captured_fields.get("pickup_address") or "").strip()
    if not clinic_name or not pickup_address:
        return {"submitted": False, "reason": "missing_clinic_or_address"}

    courier_data = None
    resolved_client_id = client_id

    if not resolved_client_id:
        try:
            matches = supabase.search_clients_by_clinic_name(clinic_name, limit=1)
        except httpx.HTTPStatusError:
            matches = []
        if len(matches) == 1:
            resolved_client_id = matches[0].get("id")

    if resolved_client_id:
        try:
            courier_data = supabase.get_assigned_courier(resolved_client_id)
        except httpx.HTTPStatusError:
            courier_data = None

    courier_name = (
        str(courier_data.get("name") or "").strip() if isinstance(courier_data, dict) else ""
    )
    now_iso = datetime.now().isoformat()
    idempotency_key = build_route_mock_idempotency_key(
        chat_id=chat_id,
        clinic_name=clinic_name,
        pickup_address=pickup_address,
        scheduled_pickup_date=scheduled_pickup_date,
    )

    mock_payload = {
        "idempotency_key": idempotency_key,
        "requested_at": now_iso,
        "programacion_ruta": clinic_name,
        "direccion": pickup_address,
        "barrio": captured_fields.get("pickup_neighborhood") or captured_fields.get("zone") or "",
        "mensajero": courier_name,
        "estado": "programada",
        "observacion": "registro_automatico_sandbox",
        "request_id": request_id,
        "client_id": resolved_client_id,
        "scheduled_pickup_date": scheduled_pickup_date,
        "source": "telegram_bot_auto",
    }

    supabase.create_request_event(
        request_id=request_id,
        event_type="route_form_mock_submitted",
        event_payload=mock_payload,
    )

    assignment_payload = {
        "request_id": request_id,
        "client_id": resolved_client_id,
        "assigned_courier_id": courier_data.get("id") if isinstance(courier_data, dict) else None,
        "priority": "normal",
    }
    assignment = assign_courier(assignment_payload)

    supabase.update_request(
        request_id,
        {
            "status": assignment.get("status") or "received",
            "assigned_courier_id": assignment.get("courier_id"),
            "fallback_reason": assignment.get("fallback_reason"),
            "updated_at": now_iso,
        },
    )
    supabase.create_request_event(
        request_id=request_id,
        event_type="assignment_result",
        event_payload={
            **assignment,
            "courier_name": courier_name,
            "idempotency_key": idempotency_key,
        },
    )

    return {
        "submitted": True,
        "idempotency_key": idempotency_key,
        "assigned": bool(assignment.get("assigned")),
        "courier_name": courier_name,
    }


def get_message_from_update(update: dict[str, Any]) -> tuple[int, str]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        raise ValueError("No message payload")

    chat = message.get("chat", {})
    text = message.get("text", "")
    chat_id = chat.get("id")

    if chat_id is None:
        raise ValueError("Missing chat id")

    return int(chat_id), text


def create_base_request(
    *,
    client_id: str | None,
    service_area: str,
    intent: str,
    priority: str,
    pickup_address: str | None,
    scheduled_pickup_date: str | None,
) -> dict[str, Any]:
    payload = {
        "client_id": client_id,
        "entry_channel": "telegram",
        "service_area": service_area,
        "intent": intent,
        "priority": priority,
        "status": "received",
        "pickup_address": pickup_address,
        "requested_at": datetime.now().isoformat(),
        "scheduled_pickup_date": scheduled_pickup_date,
    }
    new_request = supabase.create_request(payload)
    supabase.create_request_event(
        request_id=new_request["id"],
        event_type="request_received",
        event_payload={
            "service_area": service_area,
            "priority": priority,
        },
    )
    return new_request


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("is_authenticated"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def safe_fetch(method, default):
    try:
        return method()
    except httpx.HTTPStatusError:
        return default


def assignment_from_client(client: dict[str, Any]) -> dict[str, Any] | None:
    assignment_raw = client.get("client_courier_assignment")
    if isinstance(assignment_raw, list):
        return assignment_raw[0] if assignment_raw else None
    if isinstance(assignment_raw, dict):
        return assignment_raw
    return None


def format_turnaround_label(hours: int | None) -> str:
    if not hours:
        return "Por definir"
    if hours % 24 == 0:
        days = hours // 24
        return f"{days} dia(s)"
    return f"{hours} hora(s)"


def build_dashboard_context() -> dict[str, Any]:
    clients = safe_fetch(supabase.list_clients_with_assignment, [])
    requests_rows = safe_fetch(lambda: supabase.list_requests(limit=4000), [])
    conversations = safe_fetch(lambda: supabase.list_recent_conversations(limit=300), [])
    messages = safe_fetch(lambda: supabase.list_recent_messages(limit=500), [])
    catalog = safe_fetch(lambda: supabase.list_catalog_tests(limit=4000), [])
    flow_sessions = safe_fetch(lambda: supabase.list_telegram_sessions_with_client(limit=3000), [])
    flow_events = safe_fetch(
        lambda: supabase.list_recent_conversation_stage_events(limit=5000),
        [],
    )
    samples = safe_fetch(
        lambda: supabase.fetch_rows(
            "lab_samples",
            {
                "select": "id,client_id,status,priority,test_code,test_name,sample_type,created_at,estimated_ready_at,delivered_at,clients(clinic_name),couriers(name)",
                "order": "created_at.desc",
                "limit": "4000",
            },
        ),
        [],
    )

    total_clients = len(clients)
    clients_with_courier = 0
    courier_counter: Counter[str] = Counter()
    zone_counter: Counter[str] = Counter()
    request_count_by_client: Counter[str] = Counter()
    sample_count_by_client: Counter[str] = Counter()
    latest_request_by_client: dict[str, str] = {}
    latest_sample_by_client: dict[str, str] = {}

    for client in clients:
        zone = (client.get("zone") or "Sin zona").strip()
        zone_counter[zone] += 1

        assignment = assignment_from_client(client)

        if assignment:
            clients_with_courier += 1
            courier_data = assignment.get("couriers")
            courier_name = courier_data.get("name") if courier_data else "Sin mensajero"
            courier_counter[courier_name or "Sin mensajero"] += 1

    for row in requests_rows:
        client_id = row.get("client_id")
        if not client_id:
            continue
        request_count_by_client[str(client_id)] += 1
        if str(client_id) not in latest_request_by_client:
            latest_request_by_client[str(client_id)] = row.get("status") or "-"

    for row in samples:
        client_id = row.get("client_id")
        if not client_id:
            continue
        sample_count_by_client[str(client_id)] += 1
        if str(client_id) not in latest_sample_by_client:
            latest_sample_by_client[str(client_id)] = row.get("status") or "-"

    request_status_counter = Counter(row.get("status") or "unknown" for row in requests_rows)
    service_area_counter = Counter(row.get("service_area") or "unknown" for row in requests_rows)
    sample_status_counter = Counter(row.get("status") or "unknown" for row in samples)
    analysis_counter = Counter(
        (row.get("test_code") or row.get("test_name") or "Sin definir") for row in samples
    )
    flow_stage_counter = Counter(
        (row.get("phase_current") or "sin_etapa") for row in flow_sessions
    )
    flow_transition_counter: Counter[str] = Counter()
    latest_flow_event_by_chat: dict[str, dict[str, Any]] = {}

    for event in flow_events:
        from_stage = event.get("from_stage") or "inicio"
        to_stage = event.get("to_stage") or "sin_etapa"
        flow_transition_counter[f"{from_stage}->{to_stage}"] += 1

        chat_id = str(event.get("external_chat_id") or "")
        if chat_id and chat_id not in latest_flow_event_by_chat:
            latest_flow_event_by_chat[chat_id] = event

    catalog_by_code = {
        str(test.get("test_code")): test
        for test in catalog
        if test.get("test_code")
    }

    clients_rows = []
    for client in clients:
        assignment = assignment_from_client(client)
        courier_data = assignment.get("couriers") if assignment else None
        client_id = str(client.get("id"))
        clients_rows.append(
            {
                "clinic_name": client.get("clinic_name") or "-",
                "phone": client.get("phone") or "-",
                "address": client.get("address") or "-",
                "zone": client.get("zone") or "Sin zona",
                "courier_name": courier_data.get("name") if courier_data else "Sin mensajero",
                "requests_count": request_count_by_client.get(client_id, 0),
                "samples_count": sample_count_by_client.get(client_id, 0),
                "latest_request_status": latest_request_by_client.get(client_id, "-"),
                "latest_sample_status": latest_sample_by_client.get(client_id, "-"),
            }
        )

    analysis_rows = []
    for analysis_key, amount in analysis_counter.most_common(200):
        test = catalog_by_code.get(str(analysis_key), {})
        analysis_rows.append(
            {
                "analysis_code": test.get("test_code") or (analysis_key if str(analysis_key).isdigit() else "-"),
                "analysis_name": test.get("test_name") or analysis_key,
                "category": test.get("category") or "Sin categoria",
                "price_cop": test.get("price_cop"),
                "active_samples": amount,
            }
        )

    catalog_rows = []
    for test in catalog:
        delivery_text = test.get("subcategory") or format_turnaround_label(
            test.get("turnaround_hours")
        )
        catalog_rows.append(
            {
                "analysis_code": test.get("test_code") or "-",
                "test_type": test.get("category") or "Sin categoria",
                "test_name": test.get("test_name") or "Sin nombre",
                "turnaround": delivery_text,
                "price_cop": test.get("price_cop"),
            }
        )

    catalog_rows.sort(key=lambda row: str(row.get("analysis_code") or ""))

    summary_cards = {
        "total_clients": total_clients,
        "clients_with_courier": clients_with_courier,
        "clients_without_courier": max(total_clients - clients_with_courier, 0),
        "active_requests": len(requests_rows),
        "pending_pickup": sample_status_counter.get("pending_pickup", 0),
        "in_analysis": sample_status_counter.get("in_analysis", 0),
        "ready_results": sample_status_counter.get("ready_results", 0),
        "delivered_results": sample_status_counter.get("delivered_results", 0),
        "open_conversations": len([c for c in conversations if c.get("open_status") == "open"]),
        "catalog_tests": len(catalog),
        "total_samples": len(samples),
        "analysis_active_types": len(analysis_counter),
    }

    funnel_stages = [
        {"label": "Solicitudes recibidas", "value": request_status_counter.get("received", 0)},
        {"label": "Asignadas", "value": request_status_counter.get("assigned", 0)},
        {"label": "En camino", "value": request_status_counter.get("on_route", 0)},
        {"label": "En laboratorio", "value": request_status_counter.get("in_lab", 0)},
        {"label": "Procesadas", "value": request_status_counter.get("processed", 0)},
        {"label": "Resultados enviados", "value": request_status_counter.get("sent", 0)},
    ]

    top_couriers = [
        {"name": name, "clients": amount}
        for name, amount in courier_counter.most_common(10)
    ]
    top_zones = [{"zone": zone, "clients": amount} for zone, amount in zone_counter.most_common(10)]
    top_service_areas = [
        {"service_area": name, "count": amount}
        for name, amount in service_area_counter.most_common(6)
    ]

    recent_requests = requests_rows[:50]
    recent_messages = messages[:50]
    recent_samples = samples[:120]

    flow_stage_counts = [
        {
            "stage_key": stage_key,
            "label": label,
            "count": flow_stage_counter.get(stage_key, 0),
            "order": FLOW_STAGE_ORDER.get(stage_key, 999),
        }
        for stage_key, label in FLOW_STAGES
    ]
    for stage_key, amount in flow_stage_counter.items():
        if stage_key in FLOW_STAGE_LABELS:
            continue
        flow_stage_counts.append(
            {
                "stage_key": stage_key,
                "label": flow_stage_label(stage_key),
                "count": amount,
                "order": 999,
            }
        )
    flow_stage_counts.sort(key=lambda row: (row["order"], row["label"]))

    flow_transitions = []
    for transition, amount in flow_transition_counter.most_common(20):
        from_stage, to_stage = transition.split("->", maxsplit=1)
        flow_transitions.append(
            {
                "from_stage": from_stage,
                "from_label": flow_stage_label(from_stage),
                "to_stage": to_stage,
                "to_label": flow_stage_label(to_stage),
                "count": amount,
            }
        )

    flow_sessions_rows = []
    for session_row in flow_sessions:
        chat_id = str(session_row.get("external_chat_id") or "")
        client_data = session_row.get("clients") if isinstance(session_row.get("clients"), dict) else {}
        latest_event = latest_flow_event_by_chat.get(chat_id)
        flow_sessions_rows.append(
            {
                "external_chat_id": chat_id or "-",
                "clinic_name": (client_data or {}).get("clinic_name") or "Sin identificar",
                "phone": (client_data or {}).get("phone") or "-",
                "phase_current": session_row.get("phase_current") or "sin_etapa",
                "phase_label": flow_stage_label(session_row.get("phase_current") or "sin_etapa"),
                "status": session_row.get("status") or "-",
                "requires_handoff": bool(session_row.get("requires_handoff", False)),
                "handoff_area": session_row.get("handoff_area") or "none",
                "updated_at": session_row.get("updated_at") or "-",
                "last_transition": (
                    flow_stage_label(latest_event.get("to_stage")) if latest_event else "Sin cambios"
                ),
                "last_transition_at": (latest_event or {}).get("created_at") or "-",
            }
        )

    flow_sessions_by_stage: dict[str, list[dict[str, Any]]] = {}
    for session_item in flow_sessions_rows:
        stage_key = session_item.get("phase_current") or "sin_etapa"
        flow_sessions_by_stage.setdefault(stage_key, []).append(session_item)

    flow_kanban_lanes = []
    for stage in flow_stage_counts:
        stage_key = stage["stage_key"]
        cards = flow_sessions_by_stage.get(stage_key, [])
        flow_kanban_lanes.append(
            {
                "stage_key": stage_key,
                "label": stage["label"],
                "count": len(cards),
                "cards": cards,
            }
        )

    flow_summary = {
        "sessions_tracked": len(flow_sessions),
        "transitions_logged": len(flow_events),
        "sessions_handoff": len([row for row in flow_sessions if row.get("requires_handoff")]),
    }

    return {
        "summary": summary_cards,
        "funnel": funnel_stages,
        "top_couriers": top_couriers,
        "top_zones": top_zones,
        "top_service_areas": top_service_areas,
        "request_status": dict(request_status_counter),
        "sample_status": dict(sample_status_counter),
        "clients": clients,
        "requests": recent_requests,
        "conversations": conversations[:25],
        "messages": recent_messages,
        "samples": recent_samples,
        "catalog_preview": catalog[:80],
        "clients_rows": clients_rows,
        "analysis_rows": analysis_rows,
        "catalog_rows": catalog_rows,
        "flow_stage_counts": flow_stage_counts,
        "flow_transitions": flow_transitions,
        "flow_sessions_rows": flow_sessions_rows,
        "flow_kanban_lanes": flow_kanban_lanes,
        "flow_summary": flow_summary,
    }


def verify_optional_secret(expected_secret: str, received_secret: str | None) -> bool:
    if not expected_secret:
        return True
    return received_secret == expected_secret


def map_intent_to_service_area(intent: str) -> str:
    return {
        "programacion_rutas": "route_scheduling",
        "contabilidad": "accounting",
        "resultados": "results",
        "alta_cliente": "new_client",
        "no_clasificado": "unknown",
    }.get(intent, "unknown")


def is_explicit_intent_switch(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False

    explicit_triggers = (
        "ahora",
        "cambiar",
        "cambio",
        "en realidad",
        "mejor",
        "pasemos",
        "quiero",
        "necesito",
    )
    areas = (
        "contabilidad",
        "resultados",
        "programacion de ruta",
        "programar recogida de muestras",
        "consulta de resultados",
        "aclara tus pagos",
        "ruta",
        "cliente nuevo",
        "eres cliente nuevo",
        "pqrs",
        "otras consultas",
    )
    has_trigger = any(token in normalized for token in explicit_triggers)
    has_area = any(token in normalized for token in areas)
    return has_trigger and has_area


def normalize_phase(
    *,
    previous_phase: str | None,
    proposed_phase: str,
    message_mode: str,
) -> str:
    if proposed_phase not in FLOW_STAGE_ORDER:
        return previous_phase or "fase_1_clasificacion"

    if not previous_phase or previous_phase not in FLOW_STAGE_ORDER:
        return proposed_phase

    if message_mode in {"side_question", "small_talk"}:
        return previous_phase

    if proposed_phase == "fase_7_escalado":
        return proposed_phase

    prev_index = FLOW_STAGE_ORDER[previous_phase]
    proposed_index = FLOW_STAGE_ORDER[proposed_phase]
    delta = proposed_index - prev_index

    if delta > 2:
        return FLOW_STAGES[min(prev_index + 1, len(FLOW_STAGES) - 1)][0]

    if delta < -1 and message_mode != "intent_switch":
        return previous_phase

    return proposed_phase


def next_phase_from_current(current_phase: str) -> str:
    current_index = FLOW_STAGE_ORDER.get(current_phase, 1)
    if current_index >= len(FLOW_STAGES) - 1:
        return FLOW_STAGES[current_index][0]
    return FLOW_STAGES[current_index + 1][0]


def is_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in {"", "-", "none", "null", "n/a", "na"}
    return True


def merge_captured_fields(
    previous_fields: dict[str, Any] | None,
    new_fields: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    if isinstance(previous_fields, dict):
        merged.update(previous_fields)

    if not isinstance(new_fields, dict):
        return merged

    for key, value in new_fields.items():
        if is_meaningful_value(value) or key not in merged:
            merged[key] = value

    return merged


def prune_missing_fields_with_captured(
    missing_fields: list[str], captured_fields: dict[str, Any]
) -> list[str]:
    if not missing_fields:
        return []

    normalized_keys = {
        key.lower(): value for key, value in (captured_fields or {}).items() if isinstance(key, str)
    }

    def has_captured(key_name: str) -> bool:
        return is_meaningful_value(normalized_keys.get(key_name))

    cleaned: list[str] = []
    for item in missing_fields:
        label = (item or "").strip().lower()
        if not label:
            continue

        if "clinica" in label and has_captured("clinic_name"):
            continue
        if "telefono" in label and has_captured("phone"):
            continue
        if "direccion" in label and has_captured("pickup_address"):
            continue
        if "mascota" in label and has_captured("pet_name"):
            continue
        if "muestra" in label and (
            has_captured("sample_reference") or has_captured("order_reference")
        ):
            continue

        cleaned.append(item)

    return cleaned


def build_ai_state(
    *,
    session: dict[str, Any] | None,
    detected_phone: str | None,
    client: dict[str, Any] | None,
    recent_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    captured_fields: dict[str, Any] = {}
    if session and isinstance(session.get("captured_fields"), dict):
        captured_fields = dict(session["captured_fields"])
    if detected_phone:
        captured_fields["phone"] = detected_phone
    if client:
        captured_fields["clinic_name"] = client.get("clinic_name")

    history_window: list[dict[str, Any]] = []
    for item in recent_history or []:
        message_text = (item.get("message_text") or "").strip()
        direction = (item.get("direction") or "").strip().lower()
        if not message_text or direction not in {"user", "bot", "system"}:
            continue
        history_window.append(
            {
                "direction": direction,
                "message_text": message_text,
                "phase_snapshot": item.get("phase_snapshot"),
                "intent_snapshot": item.get("intent_snapshot"),
                "created_at": item.get("created_at"),
            }
        )

    return {
        "intent_current": (session or {}).get("intent_current", "no_clasificado"),
        "phase_current": (session or {}).get("phase_current", "fase_1_clasificacion"),
        "status": (session or {}).get("status", "in_progress"),
        "missing_fields": (session or {}).get("missing_fields") or [],
        "captured_fields": captured_fields,
        "recent_history": history_window,
        "client_context": {
            "client_id": client.get("id") if client else None,
            "clinic_name": client.get("clinic_name") if client else None,
        },
    }


def build_resume_question(missing_fields: list[str]) -> str:
    if not missing_fields:
        return ""

    first_field = str(missing_fields[0]).strip().lower()
    if not first_field:
        return ""

    if "telefono" in first_field:
        return "Para continuar, me confirmas tu numero de contacto?"
    if "direccion" in first_field:
        return "Para avanzar, me compartes la direccion de recogida?"
    if "zona" in first_field:
        return "Para seguir, me confirmas la zona?"
    if "mascota" in first_field:
        return "Para continuar, me confirmas el nombre de la mascota?"
    if "muestra" in first_field:
        return "Para avanzar, me compartes el numero de muestra u orden?"

    return f"Para continuar, me confirmas {first_field}?"


def should_prompt_intent_clarification(
    *,
    session: dict[str, Any] | None,
    is_first_turn: bool,
    intent: str,
    service_area: str,
    phase_current: str,
    message_mode: str,
    incoming_text: str,
) -> bool:
    if is_first_turn or not session:
        return False

    if message_mode == "intent_switch":
        return False

    explicit_area = detect_explicit_service_area(incoming_text)
    if explicit_area:
        return False

    if is_greeting_only(incoming_text):
        return True

    has_clear_intent = intent in {
        "programacion_rutas",
        "contabilidad",
        "resultados",
        "alta_cliente",
    }
    has_clear_area = service_area in {
        "route_scheduling",
        "accounting",
        "results",
        "new_client",
    }

    if has_clear_intent and has_clear_area:
        return False

    if phase_current in {"fase_0_bienvenida", "fase_1_clasificacion", "fase_2_recogida_datos"}:
        return True

    if is_small_talk_only(incoming_text):
        return True

    return False


def should_attach_route_reminder(
    *,
    is_first_turn: bool,
    service_area: str,
    phase_current: str,
    status: str,
    requires_handoff: bool,
    next_action: str,
) -> bool:
    if is_first_turn or requires_handoff:
        return False

    if service_area != "route_scheduling":
        return False

    if status in {"confirmed", "closed"}:
        if next_action == "continuar_conversacion":
            return False
        return True

    return phase_current in {
        "fase_4_confirmacion",
        "fase_5_ejecucion",
        "fase_6_cierre",
    }


def append_route_reminder(message: str) -> str:
    base_message = (message or "").strip()
    if not base_message:
        return ROUTE_REMINDER_MESSAGE

    if "forms/d/e/1FAIpQLSd2xEe2utpAefWOCf5Zc7QJHsGfB-DgupJoyQpG8oaFeTofFA/viewform" in base_message:
        return base_message

    return f"{base_message}\n\n{ROUTE_REMINDER_MESSAGE}"


def should_share_new_client_registration(
    *,
    service_area: str,
    requires_handoff: bool,
    reply: str,
) -> bool:
    if requires_handoff:
        return False

    if service_area != "new_client":
        return False

    return reply != INTENT_CLARIFICATION_MESSAGE


def apply_route_conversation_guard(
    *,
    session: dict[str, Any] | None,
    client: dict[str, Any] | None,
    text: str,
    captured_fields: dict[str, Any],
    phase_current: str,
    phase_next: str,
    status: str,
    next_action: str,
) -> tuple[str, str, str, str, list[str], dict[str, Any]]:
    clinic_name = (captured_fields.get("clinic_name") or (client or {}).get("clinic_name") or "").strip()
    pickup_address = (captured_fields.get("pickup_address") or (client or {}).get("address") or "").strip()
    if clinic_name:
        captured_fields["clinic_name"] = clinic_name
    if pickup_address:
        captured_fields["pickup_address"] = pickup_address

    last_action = (session or {}).get("next_action") or ""
    last_status = (session or {}).get("status") or ""
    normalized_text = normalize_text_value(text)

    if last_action == "solicitar_direccion_actualizada" and normalized_text:
        captured_fields["pickup_address"] = text.strip()
        captured_fields["pickup_address_confirmed"] = "true"
        return (
            "fase_4_confirmacion",
            "fase_6_cierre",
            "confirmed",
            "confirmar_programacion_ruta",
            [],
            captured_fields,
        )

    if last_action == "confirmar_direccion_retiro":
        if is_affirmative_reply(text):
            captured_fields["pickup_address_confirmed"] = "true"
            return (
                "fase_4_confirmacion",
                "fase_6_cierre",
                "confirmed",
                "confirmar_programacion_ruta",
                [],
                captured_fields,
            )

        if is_negative_reply(text):
            return (
                "fase_2_recogida_datos",
                "fase_3_validacion",
                "in_progress",
                "solicitar_direccion_actualizada",
                ["direccion de recogida"],
                captured_fields,
            )

    if last_action == "confirmar_programacion_ruta":
        return (
            "fase_6_cierre",
            "fase_6_cierre",
            "confirmed",
            "continuar_conversacion",
            [],
            captured_fields,
        )

    if last_action == "continuar_conversacion" and last_status in {"confirmed", "closed"}:
        return (
            "fase_6_cierre",
            "fase_6_cierre",
            "confirmed",
            "continuar_conversacion",
            [],
            captured_fields,
        )

    if last_action == "solicitar_cliente_y_direccion" and normalized_text:
        clinic_from_text, address_from_text = parse_clinic_and_address_from_text(text)
        if clinic_from_text and not captured_fields.get("clinic_name"):
            captured_fields["clinic_name"] = clinic_from_text
        if address_from_text:
            captured_fields["pickup_address"] = address_from_text

        if captured_fields.get("pickup_address"):
            return (
                "fase_3_validacion",
                "fase_4_confirmacion",
                "in_progress",
                "confirmar_direccion_retiro",
                ["confirmacion de direccion"],
                captured_fields,
            )

        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "solicitar_cliente_y_direccion",
            ["direccion de recogida"],
            captured_fields,
        )

    if pickup_address:
        return (
            "fase_3_validacion",
            "fase_4_confirmacion",
            "in_progress",
            "confirmar_direccion_retiro",
            ["confirmacion de direccion"],
            captured_fields,
        )

    return (
        "fase_2_recogida_datos",
        "fase_3_validacion",
        "in_progress",
        "solicitar_cliente_y_direccion",
        ["clinica", "direccion de recogida"],
        captured_fields,
    )


def handle_telegram_message(chat_id: int, text: str) -> None:
    phone = extract_phone(text)
    client = supabase.get_client_by_phone(phone) if phone else None
    if not client:
        client = identify_client_by_tax_id_or_clinic(text)
    client_id = client["id"] if client else None

    session: dict[str, Any] | None = None
    session_lookup_failed = False
    try:
        session = supabase.get_telegram_session(str(chat_id))
    except httpx.HTTPStatusError:
        session_lookup_failed = True

    if not openai_service:
        if not session_lookup_failed and session is None:
            try:
                supabase.upsert_telegram_session(
                    {
                        "channel": "telegram",
                        "external_chat_id": str(chat_id),
                        "client_id": client_id,
                        "request_id": None,
                        "intent_current": "no_clasificado",
                        "service_area": "unknown",
                        "phase_current": "fase_0_bienvenida",
                        "phase_next": "fase_1_clasificacion",
                        "status": "in_progress",
                        "missing_fields": [],
                        "captured_fields": {"phone": phone} if phone else {},
                        "ai_confidence": None,
                        "requires_handoff": False,
                        "handoff_area": "none",
                        "last_user_message": text,
                        "last_bot_message": INITIAL_GREETING_MESSAGE,
                        "next_action": "continuar_conversacion",
                        "updated_at": datetime.now().isoformat(),
                    }
                )
            except httpx.HTTPStatusError:
                print(f"[telegram] session_init_unavailable chat_id={chat_id}")

            telegram.send_message(chat_id, INITIAL_GREETING_MESSAGE)
            return

        run_legacy_flow(chat_id, text, client, client_id)
        return

    if session_lookup_failed:
        run_legacy_flow(chat_id, text, client, client_id)
        return

    is_first_turn = session is None

    previous_phase = (session or {}).get("phase_current")
    session_intent = (session or {}).get("intent_current", "no_clasificado")
    session_service_area = (session or {}).get(
        "service_area", map_intent_to_service_area(session_intent)
    )
    session_phase = (session or {}).get("phase_current", "fase_1_clasificacion")
    session_phase_next = (session or {}).get("phase_next") or "fase_2_recogida_datos"
    session_status = (session or {}).get("status", "in_progress")
    session_missing_fields = [
        str(item)
        for item in ((session or {}).get("missing_fields") or [])
        if item is not None
    ]
    session_handoff_required = bool((session or {}).get("requires_handoff", False))
    session_handoff_area = (session or {}).get("handoff_area", "none")

    if not client_id:
        client_id = (session or {}).get("client_id")

    recent_history_rows: list[dict[str, Any]] = []
    try:
        recent_history_rows = supabase.list_telegram_message_events(str(chat_id), limit=10)
    except httpx.HTTPStatusError:
        recent_history_rows = []

    recent_history_rows = list(reversed(recent_history_rows))

    ai_state = build_ai_state(
        session=session,
        detected_phone=phone,
        client=client,
        recent_history=recent_history_rows,
    )

    try:
        supabase.create_telegram_message_event(
            {
                "channel": "telegram",
                "external_chat_id": str(chat_id),
                "client_id": client_id or (session or {}).get("client_id"),
                "request_id": (session or {}).get("request_id"),
                "direction": "user",
                "message_text": text,
                "phase_snapshot": session_phase,
                "intent_snapshot": session_intent,
                "service_area_snapshot": session_service_area,
                "captured_fields_snapshot": ai_state.get("captured_fields") or {},
                "metadata": {},
                "created_at": datetime.now().isoformat(),
            }
        )
    except httpx.HTTPStatusError:
        print(f"[telegram] message_history_unavailable chat_id={chat_id}")

    try:
        turn = openai_service.generate_turn(
            system_prompt=SYSTEM_PROMPT,
            user_message=text,
            state=ai_state,
        )
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        print(f"[telegram] openai_fallback reason={type(exc).__name__} chat_id={chat_id}")
        turn = {
            "intent": "no_clasificado",
            "service_area": "unknown",
            "phase_current": "fase_1_clasificacion",
            "phase_next": "fase_2_recogida_datos",
            "status": "in_progress",
            "missing_fields": [],
            "captured_fields": ai_state.get("captured_fields") or {},
            "requires_handoff": False,
            "handoff_area": "none",
            "next_action": "continuar_conversacion",
            "message_mode": "flow_progress",
            "resume_prompt": "",
            "confidence": 0.35,
            "reply": "Gracias, te ayudo con eso.",
        }

    intent = turn.get("intent", "no_clasificado")
    if intent not in VALID_INTENTS:
        intent = "no_clasificado"
    service_area = turn.get("service_area") or map_intent_to_service_area(intent)
    pending_route_identifier = bool(
        session
        and (session or {}).get("next_action") == "solicitar_nif_o_nombre_fiscal"
        and session_service_area == "route_scheduling"
    )
    extracted_tax_id = extract_tax_id_candidate(text)
    extracted_results_reference = extract_results_reference(text)
    explicit_area = detect_explicit_service_area(text)
    if not explicit_area and session_service_area == "route_scheduling" and extracted_tax_id:
        explicit_area = "route_scheduling"
    if not explicit_area and session_service_area == "results" and extracted_results_reference:
        explicit_area = "results"
    if pending_route_identifier and explicit_area == "new_client" and not user_declares_not_registered(text):
        explicit_area = "route_scheduling"
    if not explicit_area and len(normalize_lookup_key(text)) >= 8:
        semantic_area = detect_semantic_service_area_hint(text)
        if pending_route_identifier and semantic_area == "new_client" and not user_declares_not_registered(text):
            semantic_area = None
        if semantic_area:
            explicit_area = semantic_area
    numeric_menu_option = detect_numeric_menu_option(text)
    if numeric_menu_option in {"route_scheduling", "results", "accounting", "new_client"}:
        explicit_area = numeric_menu_option
    special_menu_option = detect_special_menu_option(text)

    if explicit_area and service_area != explicit_area:
        service_area = explicit_area
        intent = {
            "route_scheduling": "programacion_rutas",
            "results": "resultados",
            "accounting": "contabilidad",
            "new_client": "alta_cliente",
        }.get(explicit_area, intent)

    if pending_route_identifier and not user_declares_not_registered(text):
        if not explicit_area or explicit_area == "route_scheduling":
            service_area = "route_scheduling"
            intent = "programacion_rutas"

    if (
        session
        and service_area == "unknown"
        and session_service_area in {"route_scheduling", "results", "accounting", "new_client"}
        and not explicit_area
        and not special_menu_option
        and not is_explicit_intent_switch(text)
    ):
        service_area = session_service_area
        intent = session_intent

    phase_current = turn.get("phase_current", "fase_1_clasificacion")
    phase_next = turn.get("phase_next", "fase_2_recogida_datos")
    status = turn.get("status", "in_progress")
    missing_fields = turn.get("missing_fields", [])
    captured_fields = turn.get("captured_fields", {})
    requires_handoff = bool(turn.get("requires_handoff", False))
    handoff_area = turn.get("handoff_area", "none")
    next_action = turn.get("next_action", "continuar_conversacion")
    message_mode = turn.get("message_mode", "flow_progress")
    if message_mode not in VALID_MESSAGE_MODES:
        message_mode = "flow_progress"
    next_action = normalize_next_action_token(
        next_action,
        service_area=service_area,
        status=status,
    )
    resume_prompt = (turn.get("resume_prompt") or "").strip()
    confidence = turn.get("confidence", 0.5)
    reply = (turn.get("reply") or "Gracias. Te ayudo con eso.").strip()
    follow_up_message = ""

    if special_menu_option == "pqrs":
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        missing_fields = []
        requires_handoff = False
        handoff_area = "none"
        next_action = "share_pqrs_link"
        message_mode = "intent_switch"
        resume_prompt = ""
        reply = PQRS_MESSAGE
        follow_up_message = INTENT_CLARIFICATION_MESSAGE

    if special_menu_option == "other_queries":
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        missing_fields = []
        requires_handoff = False
        handoff_area = "none"
        next_action = "atender_otra_consulta"
        message_mode = "intent_switch"
        resume_prompt = ""
        reply = OTHER_QUERIES_MESSAGE

    if service_area == "unknown" and special_menu_option is None:
        recovery_area = detect_explicit_service_area(text) or detect_semantic_service_area_hint(text)
        if recovery_area in {"route_scheduling", "results", "accounting", "new_client"}:
            service_area = recovery_area
            intent = {
                "route_scheduling": "programacion_rutas",
                "results": "resultados",
                "accounting": "contabilidad",
                "new_client": "alta_cliente",
            }.get(recovery_area, intent)
            if next_action in {"atender_otra_consulta", "solicitar_clasificacion"}:
                next_action = normalize_next_action_token(
                    "continuar_conversacion",
                    service_area=service_area,
                    status=status,
                )

    if not isinstance(captured_fields, dict):
        captured_fields = {}

    captured_fields = merge_captured_fields(ai_state.get("captured_fields"), captured_fields)

    missing_fields = [str(item) for item in missing_fields if item is not None]
    missing_fields = prune_missing_fields_with_captured(missing_fields, captured_fields)
    intent_changed = bool(session and intent != session_intent)

    if session and intent_changed and message_mode != "intent_switch":
        explicit_area = detect_explicit_service_area(text)
        numeric_menu_option = detect_numeric_menu_option(text)
        if numeric_menu_option in {"route_scheduling", "results", "accounting", "new_client"}:
            explicit_area = numeric_menu_option
        pending_identifier = (session or {}).get("next_action") == "solicitar_nif_o_nombre_fiscal"
        if not is_explicit_intent_switch(text) and not explicit_area and not pending_identifier:
            message_mode = "side_question"
            intent = session_intent
            service_area = session_service_area

    phase_current = normalize_phase(
        previous_phase=session_phase if session else None,
        proposed_phase=phase_current,
        message_mode=message_mode,
    )
    if phase_next not in FLOW_STAGE_ORDER:
        phase_next = next_phase_from_current(phase_current)

    if session and message_mode in {"side_question", "small_talk"}:
        intent = session_intent
        service_area = session_service_area
        phase_current = session_phase
        phase_next = session_phase_next
        status = session_status
        requires_handoff = session_handoff_required
        handoff_area = session_handoff_area
        if not missing_fields:
            missing_fields = session_missing_fields

        if not resume_prompt:
            resume_prompt = build_resume_question(missing_fields)

        if resume_prompt:
            reply = f"{reply} {resume_prompt}".strip()

    if service_area == "results":
        reference_data = extract_results_reference(text)
        if reference_data:
            captured_fields = {**captured_fields, **reference_data}
            missing_fields = clear_results_missing_fields(
                [str(item) for item in missing_fields if item is not None]
            )
            missing_fields = prune_missing_fields_with_captured(missing_fields, captured_fields)
            if phase_current == "fase_1_clasificacion":
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                reply = (
                    "Perfecto, ya tengo ese dato. Estoy validando el estado del resultado "
                    "y te confirmo enseguida."
                )

        if not captured_fields.get("clinic_name"):
            clinic_hint = extract_clinic_name_hint(text)
            if clinic_hint:
                search_a3_knowledge = getattr(supabase, "search_a3_knowledge_by_clinic_name", None)
                if callable(search_a3_knowledge):
                    try:
                        raw_matches = search_a3_knowledge(clinic_hint, limit=1)
                    except httpx.HTTPStatusError:
                        raw_matches = []
                    knowledge_matches = ensure_dict_rows(raw_matches)
                    if knowledge_matches:
                        first_match = knowledge_matches[0]
                        clinic_name_match = (first_match.get("clinic_name") or "").strip()
                        clinic_key_match = (first_match.get("clinic_key") or "").strip()
                        if clinic_name_match:
                            captured_fields["clinic_name"] = clinic_name_match
                        if clinic_key_match:
                            captured_fields["knowledge_clinic_key"] = clinic_key_match

        clinic_key = str(captured_fields.get("knowledge_clinic_key") or "").strip()
        if clinic_key and not captured_fields.get("sample_reference") and not captured_fields.get("order_reference"):
            status_summary = summarize_a3_sample_status(clinic_key)
            if status_summary:
                submitted_count = int(status_summary.get("submitted", 0))
                pending_count = int(status_summary.get("pending_issue", 0))
                top_reason = str(status_summary.get("top_reason") or "").strip()
                clinic_label = captured_fields.get("clinic_name") or "tu clinica"
                if pending_count > 0:
                    reason_suffix = f" Motivo mas frecuente: {top_reason}." if top_reason else ""
                    reply = (
                        f"Tengo trazabilidad reciente para {clinic_label}: "
                        f"{pending_count} muestras con novedad y {submitted_count} registradas sin novedad.{reason_suffix} "
                        "Si me compartes el numero de muestra u orden, te doy el estado puntual."
                    )
                else:
                    reply = (
                        f"Tengo trazabilidad reciente para {clinic_label}: "
                        f"{submitted_count} registros sin novedades reportadas. "
                        "Si me compartes el numero de muestra u orden, te doy el estado puntual."
                    )

    if is_first_turn:
        if is_wellbeing_greeting(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
            next_action = "solicitar_clasificacion"
            phase_current = "fase_1_clasificacion"
        elif should_split_first_greeting(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
            next_action = "solicitar_clasificacion"
            phase_current = "fase_1_clasificacion"
        else:
            reply = INITIAL_GREETING_MESSAGE
            phase_current = "fase_0_bienvenida"
        phase_next = "fase_1_clasificacion"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        message_mode = "small_talk"
        resume_prompt = ""

    if should_prompt_intent_clarification(
        session=session,
        is_first_turn=is_first_turn,
        intent=intent,
        service_area=service_area,
        phase_current=phase_current,
        message_mode=message_mode,
        incoming_text=text,
    ):
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "solicitar_clasificacion"
        missing_fields = []
        resume_prompt = ""
        message_mode = "flow_progress"
        if is_wellbeing_greeting(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
        elif is_greeting_only(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
        else:
            reply = INTENT_CLARIFICATION_MESSAGE

    if (
        not is_first_turn
        and service_area == "route_scheduling"
        and not requires_handoff
        and not client_id
        and not is_meaningful_value(captured_fields.get("clinic_name"))
        and reply != INTENT_CLARIFICATION_MESSAGE
    ):
        identified_client = identify_client_by_tax_id_or_clinic(text)
        if identified_client:
            client = identified_client
            client_id = identified_client.get("id")
            clinic_name = identified_client.get("clinic_name")
            tax_id = identified_client.get("tax_id")
            phone_registered = identified_client.get("phone")
            if clinic_name:
                captured_fields["clinic_name"] = clinic_name
            if tax_id:
                captured_fields["tax_id"] = tax_id
            if phone_registered:
                captured_fields["phone"] = phone_registered
        elif user_declares_not_registered(text):
            captured_fields["post_registration_service_area"] = "route_scheduling"
            captured_fields["post_registration_intent"] = "programacion_rutas"
            service_area = "new_client"
            intent = "alta_cliente"
            phase_current = "fase_2_recogida_datos"
            phase_next = "fase_3_validacion"
            status = "in_progress"
            next_action = "compartir_formulario_registro_cliente"
            message_mode = "flow_progress"
            resume_prompt = ""
            missing_fields = []
            reply = NEW_CLIENT_REGISTRATION_MESSAGE
        else:
            attempts = int(captured_fields.get("route_identification_attempts", 0) or 0) + 1
            captured_fields["route_identification_attempts"] = attempts

            if is_price_or_services_inquiry(text) or is_help_inquiry(text):
                service_area = "unknown"
                intent = "no_clasificado"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "atender_otra_consulta"
                message_mode = "intent_switch"
                resume_prompt = ""
                missing_fields = []
                reply = (
                    "Claro, puedo orientarte con servicios, precios aproximados y procesos del laboratorio. "
                    "Cuéntame qué examen o necesidad tienes y te ayudo de inmediato."
                )
            elif attempts >= 3:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF o nombre fiscal de la veterinaria"]
                reply = (
                    "Aun no logro ubicar tu registro. Para continuar, envíame uno de estos datos:\n"
                    "- NIF/NIT (ejemplo: 900123456)\n"
                    "- Nombre de la veterinaria (ejemplo: Terra Pets)\n"
                    "Si prefieres otra gestión, escribe 2, 3, 4, 5 o 6 del menú."
                )
            elif attempts == 2:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF o nombre fiscal de la veterinaria"]
                reply = (
                    "Para ubicarte rápido, compárteme por favor uno de estos datos:\n"
                    "- NIF/NIT\n"
                    "- Nombre fiscal de la veterinaria"
                )
            else:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF o nombre fiscal de la veterinaria"]
                reply = ROUTE_CLIENT_IDENTIFICATION_MESSAGE

    if (
        not is_first_turn
        and service_area == "route_scheduling"
        and not requires_handoff
        and (client_id or is_meaningful_value(captured_fields.get("clinic_name")))
        and reply != INTENT_CLARIFICATION_MESSAGE
    ):
        last_session_action = (session or {}).get("next_action") or ""
        explicit_switch_area = detect_explicit_service_area(text)
        special_option = detect_special_menu_option(text)

        if last_session_action in {"confirmar_programacion_ruta", "continuar_conversacion"}:
            if special_option == "pqrs":
                intent = "no_clasificado"
                service_area = "unknown"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "share_pqrs_link"
                missing_fields = []
                message_mode = "flow_progress"
                resume_prompt = ""
                reply = PQRS_MESSAGE
                follow_up_message = INTENT_CLARIFICATION_MESSAGE
            elif is_price_or_services_inquiry(text) or is_help_inquiry(text):
                intent = "no_clasificado"
                service_area = "unknown"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "atender_otra_consulta"
                missing_fields = []
                message_mode = "intent_switch"
                resume_prompt = ""
                reply = (
                    "Claro, puedo orientarte con servicios, precios aproximados y procesos del laboratorio. "
                    "Cuéntame qué examen o necesidad tienes y te ayudo de inmediato."
                )
            elif special_option == "other_queries":
                intent = "no_clasificado"
                service_area = "unknown"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "atender_otra_consulta"
                missing_fields = []
                message_mode = "intent_switch"
                resume_prompt = ""
                reply = OTHER_QUERIES_MESSAGE
            elif explicit_switch_area and explicit_switch_area != "route_scheduling":
                service_area = explicit_switch_area
                intent = {
                    "results": "resultados",
                    "accounting": "contabilidad",
                    "new_client": "alta_cliente",
                }.get(explicit_switch_area, intent)

                if service_area == "results":
                    next_action = "continuar_conversacion"
                    missing_fields = ["numero de muestra o nombre mascota"]
                    reply = "Perfecto, te ayudo con resultados. Compárteme el número de muestra u orden."
                elif service_area == "accounting":
                    next_action = "continuar_conversacion"
                    missing_fields = []
                    reply = "Perfecto, te ayudo con pagos y contabilidad. Cuéntame el detalle de tu caso."
                elif service_area == "new_client":
                    next_action = "compartir_formulario_registro_cliente"
                    missing_fields = []
                    reply = NEW_CLIENT_REGISTRATION_MESSAGE

        if "route_identification_attempts" in captured_fields:
            captured_fields["route_identification_attempts"] = 0

        if service_area == "route_scheduling":
            phase_current, phase_next, status, next_action, missing_fields, captured_fields = apply_route_conversation_guard(
                session=session,
                client=client,
                text=text,
                captured_fields=captured_fields,
                phase_current=phase_current,
                phase_next=phase_next,
                status=status,
                next_action=next_action,
            )

            if next_action == "confirmar_direccion_retiro":
                clinic_label = captured_fields.get("clinic_name") or "tu veterinaria"
                address_label = captured_fields.get("pickup_address") or "la direccion registrada"
                reply = (
                    "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                    f"¿Confirmas que el retiro es para {clinic_label} en {address_label}?"
                )
            elif next_action == "solicitar_direccion_actualizada":
                reply = "Perfecto, por favor comparteme la direccion actual para programar el retiro."
            elif next_action == "confirmar_programacion_ruta":
                if (session or {}).get("next_action") == "solicitar_direccion_actualizada":
                    reply = (
                        "Listo, registre la nueva direccion de retiro y tu solicitud quedo programada. "
                        "Te confirmaremos cualquier novedad por este medio."
                    )
                else:
                    reply = (
                        "Listo, tu solicitud de retiro de muestra quedo programada. "
                        "Te confirmaremos cualquier novedad por este medio."
                    )
            elif next_action == "continuar_conversacion":
                reply = (
                    "Tu solicitud ya quedó programada. "
                    "Si deseas, puedo ayudarte ahora con resultados, pagos, PQRS u otra consulta."
                )
            else:
                needs_clinic = not is_meaningful_value(captured_fields.get("clinic_name"))
                needs_address = not is_meaningful_value(captured_fields.get("pickup_address"))
                if needs_clinic and needs_address:
                    reply = (
                        "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                        "Por favor comparteme el nombre de la veterinaria y la direccion de retiro."
                    )
                elif needs_address:
                    reply = "Perfecto, por favor comparteme la direccion de retiro para programar la ruta."
                elif needs_clinic:
                    reply = "Perfecto, por favor confirmame el nombre de la veterinaria para continuar."
                else:
                    clinic_label = captured_fields.get("clinic_name") or "tu veterinaria"
                    address_label = captured_fields.get("pickup_address") or "la direccion registrada"
                    reply = (
                        "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                        f"¿Confirmas que el retiro es para {clinic_label} en {address_label}?"
                    )

            resume_prompt = ""
            message_mode = "flow_progress"

    if should_share_new_client_registration(
        service_area=service_area,
        requires_handoff=requires_handoff,
        reply=reply,
    ):
        reply = NEW_CLIENT_REGISTRATION_MESSAGE
        next_action = "compartir_formulario_registro_cliente"
        message_mode = "flow_progress"
        resume_prompt = ""
        missing_fields = []

    if (
        not is_first_turn
        and service_area == "new_client"
        and user_confirms_registration_completed(text)
    ):
        pending_service_area, pending_intent = get_pending_post_registration_target(captured_fields)
        captured_fields = clear_post_registration_target(captured_fields)

        if pending_service_area == "route_scheduling":
            intent = pending_intent or "programacion_rutas"
            service_area = "route_scheduling"
            phase_current = "fase_2_recogida_datos"
            phase_next = "fase_3_validacion"
            status = "in_progress"
            requires_handoff = False
            handoff_area = "none"
            next_action = "solicitar_nif_o_nombre_fiscal"
            missing_fields = ["NIF o nombre fiscal de la veterinaria"]
            message_mode = "flow_progress"
            resume_prompt = ""
            reply = NEW_CLIENT_POST_REGISTRATION_ROUTE_MESSAGE
        else:
            intent = "no_clasificado"
            service_area = "unknown"
            phase_current = "fase_1_clasificacion"
            phase_next = "fase_2_recogida_datos"
            status = "in_progress"
            requires_handoff = False
            handoff_area = "none"
            next_action = "solicitar_clasificacion"
            missing_fields = []
            message_mode = "flow_progress"
            resume_prompt = ""
            reply = NEW_CLIENT_POST_REGISTRATION_MESSAGE

    if should_attach_route_reminder(
        is_first_turn=is_first_turn,
        service_area=service_area,
        phase_current=phase_current,
        status=status,
        requires_handoff=requires_handoff,
        next_action=next_action,
    ):
        reply = append_route_reminder(reply)

    last_bot_message_to_store = follow_up_message or reply

    previous_bot_message = ((session or {}).get("last_bot_message") or "").strip().lower()
    if previous_bot_message and reply.strip().lower() == previous_bot_message:
        if reply.startswith("Perfecto, te ayudo con la programacion de ruta"):
            anti_loop_prompt = build_resume_question(missing_fields)
            if not anti_loop_prompt:
                anti_loop_prompt = "Si te parece bien, avanzamos con este paso y lo dejamos listo."
        elif service_area == "results":
            reply = (
                "Para ayudarte con resultados sin demoras, comparteme por favor el numero de muestra "
                "o el numero de orden."
            )
            anti_loop_prompt = ""
        elif NEW_CLIENT_REGISTRATION_FORM_URL in reply:
            reply = (
                "Cuando completes el formulario de registro, me avisas y te acompano "
                "con la programacion de ruta o con lo que necesites."
            )
            anti_loop_prompt = ""
        else:
            anti_loop_prompt = build_resume_question(missing_fields)
        if anti_loop_prompt and anti_loop_prompt.lower() not in reply.lower():
            reply = f"{reply} {anti_loop_prompt}".strip()

    if phase_next not in FLOW_STAGE_ORDER:
        phase_next = next_phase_from_current(phase_current)

    if phone and isinstance(captured_fields, dict) and "phone" not in captured_fields:
        captured_fields["phone"] = phone

    scheduled_pickup_date = (
        calculate_schedule(datetime.now().isoformat(), settings.cutoff_time)[
            "scheduled_pickup_date"
        ]
        if service_area == "route_scheduling"
        else None
    )

    request_ref = create_base_request(
        client_id=client_id,
        service_area=service_area,
        intent=intent,
        priority="normal",
        pickup_address=None,
        scheduled_pickup_date=scheduled_pickup_date,
    )

    automation_note = ""
    is_route_programmed_reply = "quedo programada" in reply.lower()
    if service_area == "route_scheduling" and (
        next_action == "confirmar_programacion_ruta" or is_route_programmed_reply
    ):
        try:
            mock_result = submit_route_mock_record(
                chat_id=chat_id,
                request_id=request_ref["id"],
                client_id=client_id,
                captured_fields=captured_fields,
                scheduled_pickup_date=scheduled_pickup_date,
            )
            if mock_result.get("submitted") and mock_result.get("assigned"):
                courier_name = str(mock_result.get("courier_name") or "").strip()
                if courier_name:
                    automation_note = f" Mensajero asignado: {courier_name}."
            elif mock_result.get("submitted"):
                automation_note = (
                    " Recibimos la solicitud y quedo registrada. Estamos validando mensajero asignado."
                )
        except httpx.HTTPStatusError:
            automation_note = " Tu solicitud quedo creada, pero estamos validando la asignacion de mensajero."

    if automation_note:
        reply = f"{reply}{automation_note}".strip()
        last_bot_message_to_store = follow_up_message or reply

    try:
        supabase.upsert_telegram_session(
            {
                "channel": "telegram",
                "external_chat_id": str(chat_id),
                "client_id": client_id,
                "request_id": request_ref["id"],
                "intent_current": intent,
                "service_area": service_area,
                "phase_current": phase_current,
                "phase_next": phase_next,
                "status": status,
                "missing_fields": missing_fields,
                "captured_fields": captured_fields,
                "ai_confidence": confidence,
                "requires_handoff": requires_handoff,
                "handoff_area": handoff_area,
                "last_user_message": text,
                "last_bot_message": last_bot_message_to_store,
                "next_action": next_action,
                "updated_at": datetime.now().isoformat(),
            }
        )
        supabase.create_request_event(
            request_id=request_ref["id"],
            event_type="ai_phase_update",
            event_payload={
                "intent": intent,
                "phase_current": phase_current,
                "phase_next": phase_next,
                "status": status,
                "missing_fields": missing_fields,
                "requires_handoff": requires_handoff,
                "handoff_area": handoff_area,
                "next_action": next_action,
                "message_mode": message_mode,
                "resume_prompt": resume_prompt,
                "confidence": confidence,
            },
        )
        if requires_handoff:
            supabase.create_request_event(
                request_id=request_ref["id"],
                event_type="human_handoff",
                event_payload={"target": handoff_area},
            )

        try:
            supabase.create_telegram_message_event(
                {
                    "channel": "telegram",
                    "external_chat_id": str(chat_id),
                    "client_id": client_id,
                    "request_id": request_ref["id"],
                    "direction": "bot",
                    "message_text": reply,
                    "phase_snapshot": phase_current,
                    "intent_snapshot": intent,
                    "service_area_snapshot": service_area,
                    "captured_fields_snapshot": captured_fields,
                    "metadata": {
                        "message_mode": message_mode,
                        "resume_prompt": resume_prompt,
                        "follow_up_message": follow_up_message,
                    },
                    "created_at": datetime.now().isoformat(),
                }
            )

            if follow_up_message:
                supabase.create_telegram_message_event(
                    {
                        "channel": "telegram",
                        "external_chat_id": str(chat_id),
                        "client_id": client_id,
                        "request_id": request_ref["id"],
                        "direction": "bot",
                        "message_text": follow_up_message,
                        "phase_snapshot": phase_current,
                        "intent_snapshot": intent,
                        "service_area_snapshot": service_area,
                        "captured_fields_snapshot": captured_fields,
                        "metadata": {
                            "message_mode": "flow_progress",
                            "sent_as_follow_up": True,
                        },
                        "created_at": datetime.now().isoformat(),
                    }
                )
        except httpx.HTTPStatusError:
            print(f"[telegram] message_history_insert_failed chat_id={chat_id}")
    except httpx.HTTPStatusError:
        print(f"[telegram] supabase_session_fallback chat_id={chat_id}")
        run_legacy_flow(chat_id, text, client, client_id)
        return

    if previous_phase != phase_current:
        try:
            supabase.create_conversation_stage_event(
                {
                    "channel": "telegram",
                    "external_chat_id": str(chat_id),
                    "client_id": client_id,
                    "request_id": request_ref["id"],
                    "from_stage": previous_phase,
                    "to_stage": phase_current,
                    "trigger_source": "openai_turn",
                    "trigger_message": text,
                    "created_at": datetime.now().isoformat(),
                }
            )
        except httpx.HTTPStatusError:
            print(f"[telegram] stage_event_insert_failed chat_id={chat_id}")

    telegram.send_message(chat_id, reply)
    if follow_up_message:
        telegram.send_message(chat_id, follow_up_message)


def process_telegram_update(update: dict[str, Any]) -> None:
    try:
        chat_id, text = get_message_from_update(update)
    except ValueError:
        return
    handle_telegram_message(chat_id, text)


def run_legacy_flow(chat_id: int, text: str, client: dict[str, Any] | None, client_id: str | None) -> None:
    routed = route_message(text)

    if routed["service_area"] == "route_scheduling":
        scheduled = calculate_schedule(datetime.now().isoformat(), settings.cutoff_time)
        route_request = create_base_request(
            client_id=client_id,
            service_area="route_scheduling",
            intent="pickup_request",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=scheduled["scheduled_pickup_date"],
        )

        if client_id:
            assigned_courier_id = supabase.get_assigned_courier_id(client_id)
            assignment = assign_courier(
                {
                    "request_id": route_request["id"],
                    "client_id": client_id,
                    "assigned_courier_id": assigned_courier_id,
                    "priority": "normal",
                }
            )
            supabase.update_request(
                route_request["id"],
                {
                    "status": assignment["status"],
                    "assigned_courier_id": assignment["courier_id"],
                    "fallback_reason": assignment["fallback_reason"],
                },
            )
            supabase.create_request_event(
                request_id=route_request["id"],
                event_type="assignment_result",
                event_payload=assignment,
            )

            if assignment["assigned"]:
                telegram.send_message(
                    chat_id,
                    append_route_reminder(
                        "Solicitud recibida. Tu mensajero fue asignado correctamente."
                    ),
                )
            else:
                telegram.send_message(
                    chat_id,
                    append_route_reminder(
                        "Solicitud recibida. Estamos validando mensajero y te confirmamos en breve."
                    ),
                )
        else:
            supabase.update_request(
                route_request["id"],
                {"fallback_reason": "client_not_identified_by_phone"},
            )
            supabase.create_request_event(
                request_id=route_request["id"],
                event_type="client_identification_required",
                event_payload={"message": text},
            )
            telegram.send_message(
                chat_id,
                ROUTE_CLIENT_IDENTIFICATION_MESSAGE,
            )

    elif routed["service_area"] == "accounting":
        accounting_request = create_base_request(
            client_id=client_id,
            service_area="accounting",
            intent="human_support",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=None,
        )
        supabase.create_request_event(
            request_id=accounting_request["id"],
            event_type="human_handoff",
            event_payload={"target": "accounting"},
        )
        telegram.send_message(
            chat_id,
            "Te comunicamos con el area de contabilidad. Un asesor te responde pronto.",
        )

    elif routed["service_area"] == "results":
        results_request = create_base_request(
            client_id=client_id,
            service_area="results",
            intent="result_inquiry",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=None,
        )
        supabase.create_request_event(
            request_id=results_request["id"],
            event_type="results_inquiry",
            event_payload={"message": text},
        )
        telegram.send_message(
            chat_id,
            "Recibimos tu consulta de resultados. Te compartimos estado en breve.",
        )

    elif routed["service_area"] == "new_client":
        new_client_request = create_base_request(
            client_id=None,
            service_area="new_client",
            intent="new_client_onboarding",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=None,
        )
        supabase.create_request_event(
            request_id=new_client_request["id"],
            event_type="new_client_started",
            event_payload={"message": text},
        )
        telegram.send_message(
            chat_id,
            NEW_CLIENT_REGISTRATION_MESSAGE,
        )

    else:
        unknown_request = create_base_request(
            client_id=client_id,
            service_area="unknown",
            intent="unknown",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=None,
        )
        supabase.create_request_event(
            request_id=unknown_request["id"],
            event_type="unknown_intent",
            event_payload={"message": text},
        )
        telegram.send_message(
            chat_id,
            "Gracias. Te derivo con un asesor para ayudarte mejor.",
        )


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.route("/login", methods=["GET", "POST"])
def login() -> Any:
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if (
            username == settings.dashboard_admin_user
            and password == settings.dashboard_admin_password
        ):
            session["is_authenticated"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Credenciales invalidas")

    return render_template("login.html", error=None)


@app.get("/logout")
def logout() -> Any:
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def root() -> Any:
    if session.get("is_authenticated"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="dashboard",
    )


@app.get("/clientes")
@login_required
def clients_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="clientes",
    )


@app.get("/muestras")
@login_required
def samples_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="muestras",
    )


@app.get("/analisis")
@login_required
def analysis_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="analisis",
    )


@app.get("/flujo")
@login_required
def flow_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="flujo",
    )


@app.get("/api/dashboard/overview")
@login_required
def dashboard_overview() -> Any:
    return jsonify(build_dashboard_context())


@app.post("/webhooks/new-client-registration")
def new_client_registration_webhook() -> Any:
    secret = request.headers.get("X-New-Client-Secret")
    if not verify_optional_secret(settings.new_client_form_webhook_secret, secret):
        return jsonify({"error": "Invalid new client webhook secret"}), 401

    raw_payload = request.get_json(silent=True) or {}
    payload = raw_payload.get("responses") if isinstance(raw_payload, dict) and isinstance(raw_payload.get("responses"), dict) else raw_payload
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    clinic_name = extract_form_value(
        payload,
        (
            "Nombre de la veterinaria o medico veterinario",
            "Veterinaria o medico veterinario",
            "Nombre completo de la veterinaria",
            "clinica veterinaria",
        ),
    )
    if not clinic_name:
        return jsonify({"error": "Missing clinic name"}), 400

    clinic_key = normalize_lookup_key(clinic_name)
    if not clinic_key:
        return jsonify({"error": "Invalid clinic name"}), 400

    address = extract_form_value(
        payload,
        ("Direccion y ubicacion en Google Maps", "Direccion", "Direccion, Barrio y Localidad"),
    )
    locality = extract_form_value(payload, ("Barrio y Localidad", "Barrio y localidad"))
    phone = extract_form_value(payload, ("N Celular", "Celular o Telefono", "N Celular de comunicacion"))
    email = extract_form_value(payload, ("Email", "Correo o WhatsApp", "Correo"))
    tax_id = extract_form_value(payload, ("Rut", "Informacion en RUT", "NIT", "Nif"))
    professional_name = extract_form_value(
        payload,
        ("Medico Veterinario", "Nombre completo del medico", "Medico veterinario"),
    )
    professional_card = extract_form_value(
        payload,
        ("N Tarjeta Profesional", "N TP", "N Tarjeta profesional"),
    )
    result_delivery_mode = extract_form_value(
        payload,
        (
            "Medio de envio de Resultados",
            "Medio de envio de examenes",
            "Medio por el cual requiere que se envio los resultados",
        ),
    )

    now_iso = datetime.now().isoformat()

    knowledge_row = {
        "clinic_key": clinic_key,
        "clinic_name": clinic_name,
        "is_registered": True,
        "is_new_client": True,
        "address": address or None,
        "locality": locality or None,
        "phone": phone or None,
        "email": email or None,
        "payment_policy": None,
        "result_delivery_mode": result_delivery_mode or None,
        "sources_json": ["google_form_webhook"],
        "source_excel": "google_form_webhook",
        "source_updated_at": now_iso,
    }

    professional_row = {
        "clinic_key": clinic_key,
        "professional_key": normalize_lookup_key(f"{professional_name}|{professional_card}"),
        "professional_name": professional_name or None,
        "professional_card": professional_card or None,
        "source_sheet": "google_form_webhook",
    }

    try:
        supabase.insert_rows(
            "clients_a3_knowledge",
            [knowledge_row],
            upsert=True,
            on_conflict="clinic_key",
        )
        if professional_row["professional_key"]:
            supabase.insert_rows(
                "clients_a3_professionals",
                [professional_row],
                upsert=True,
                on_conflict="clinic_key,professional_key,source_sheet",
            )

        if address:
            base_client_payload = {
                "clinic_name": clinic_name,
                "tax_id": tax_id or None,
                "phone": phone or None,
                "address": address,
                "city": locality or None,
                "zone": locality or None,
                "billing_type": "cash",
                "is_active": True,
            }
            if phone:
                supabase.insert_rows(
                    "clients",
                    [base_client_payload],
                    upsert=True,
                    on_conflict="phone",
                )
            else:
                supabase.insert_rows("clients", [base_client_payload])
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Supabase tables are not ready for new client registration sync",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify(
        {
            "ok": True,
            "clinic_key": clinic_key,
            "clinic_name": clinic_name,
            "registered_in_clients": bool(address),
        }
    )


@app.post("/webhooks/liveconnect")
def liveconnect_webhook() -> Any:
    secret = request.headers.get("X-LiveConnect-Secret")
    if not verify_optional_secret(settings.liveconnect_webhook_secret, secret):
        return jsonify({"error": "Invalid LiveConnect secret"}), 401

    payload = request.get_json(silent=True) or {}
    conversation_external_id = payload.get("conversation_id")
    contact = payload.get("contact")
    customer_name = payload.get("customer_name")
    open_status = payload.get("open_status", "open")
    summary = payload.get("summary")
    timestamp = payload.get("timestamp") or datetime.now().isoformat()

    try:
        conv_rows = supabase.insert_rows(
            "liveconnect_conversations",
            [
                {
                    "external_conversation_id": conversation_external_id,
                    "channel": "liveconnect",
                    "external_contact": contact,
                    "customer_name": customer_name,
                    "open_status": open_status,
                    "conversation_summary": summary,
                    "last_message_at": timestamp,
                    "first_message_at": timestamp,
                }
            ],
            upsert=True,
            on_conflict="external_conversation_id",
        )
        conversation_id = conv_rows[0]["id"]

        supabase.insert_rows(
            "liveconnect_messages",
            [
                {
                    "conversation_id": conversation_id,
                    "external_message_id": payload.get("message_id"),
                    "direction": payload.get("direction", "inbound"),
                    "agent_name": payload.get("agent_name"),
                    "intent_tag": payload.get("intent_tag"),
                    "message_text": payload.get("message_text", ""),
                    "raw_payload": payload,
                }
            ],
        )
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "LiveConnect tables are not ready in Supabase",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )
    return jsonify({"ok": True})


@app.post("/webhooks/anarvet/result")
def anarvet_result_webhook() -> Any:
    secret = request.headers.get("X-Anarvet-Secret")
    if not verify_optional_secret(settings.anarvet_webhook_secret, secret):
        return jsonify({"error": "Invalid Anarvet secret"}), 401

    payload = request.get_json(silent=True) or {}
    request_id = payload.get("request_id")
    status = payload.get("status", "ready_results")

    if request_id:
        try:
            sample_rows = supabase.fetch_rows(
                "lab_samples",
                {"request_id": f"eq.{request_id}", "select": "id", "limit": "1"},
            )
            if sample_rows:
                sample_id = sample_rows[0]["id"]
                supabase.insert_rows(
                    "lab_sample_events",
                    [
                        {
                            "sample_id": sample_id,
                            "event_type": "anarvet_result_sync",
                            "event_payload": payload,
                        }
                    ],
                )
                supabase.update_rows(
                    "lab_samples",
                    {"id": f"eq.{sample_id}"},
                    {"status": status, "updated_at": datetime.now().isoformat()},
                )
        except httpx.HTTPStatusError as exc:
            return (
                jsonify(
                    {
                        "error": "Anarvet tables are not ready in Supabase",
                        "status_code": exc.response.status_code,
                    }
                ),
                503,
            )

    return jsonify({"ok": True})


@app.post("/webhooks/telegram")
def telegram_webhook() -> Any:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        return jsonify({"error": "Invalid Telegram secret token"}), 401

    update = request.get_json(silent=True) or {}

    try:
        process_telegram_update(update)
    except Exception as exc:
        print(f"[telegram] webhook_error reason={type(exc).__name__}")
        return jsonify({"ok": True}), 200

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
