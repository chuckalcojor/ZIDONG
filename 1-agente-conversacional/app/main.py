from __future__ import annotations

import re
import json
import hashlib
import time
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
from app.services.whatsapp_service import WhatsAppService
from app.dashboard_data import load_mock_dashboard_context

app = Flask(__name__)
app.secret_key = settings.flask_secret_key
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["TEMPLATES_AUTO_RELOAD"] = True

supabase = SupabaseService(
    base_url=settings.supabase_url,
    service_role_key=settings.supabase_service_role_key,
)
telegram = TelegramService(bot_token=settings.telegram_bot_token)
whatsapp_service = (
    WhatsAppService(
        access_token=settings.whatsapp_access_token,
        phone_number_id=settings.whatsapp_phone_number_id,
    )
    if settings.whatsapp_access_token and settings.whatsapp_phone_number_id
    else None
)
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
OPENAI_FAILURE_STREAK = 0
OPENAI_CIRCUIT_UNTIL = 0.0
OPENAI_CIRCUIT_THRESHOLD = 3
OPENAI_CIRCUIT_SECONDS = 120
OPENAI_WARMUP_DONE = False

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


def build_openai_fallback_turn(ai_state: dict[str, Any]) -> dict[str, Any]:
    return {
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


def openai_circuit_active() -> bool:
    return time.time() < OPENAI_CIRCUIT_UNTIL


def register_openai_success() -> None:
    global OPENAI_FAILURE_STREAK, OPENAI_CIRCUIT_UNTIL
    OPENAI_FAILURE_STREAK = 0
    OPENAI_CIRCUIT_UNTIL = 0.0


def register_openai_failure() -> None:
    global OPENAI_FAILURE_STREAK, OPENAI_CIRCUIT_UNTIL
    OPENAI_FAILURE_STREAK += 1
    if OPENAI_FAILURE_STREAK >= OPENAI_CIRCUIT_THRESHOLD:
        OPENAI_CIRCUIT_UNTIL = time.time() + OPENAI_CIRCUIT_SECONDS


def ensure_openai_warmup() -> None:
    global OPENAI_WARMUP_DONE
    if OPENAI_WARMUP_DONE:
        return
    OPENAI_WARMUP_DONE = True

    if openai_service is None:
        return

    health_check = getattr(openai_service, "quick_health_check", None)
    if not callable(health_check):
        return

    if health_check(timeout=4):
        register_openai_success()
        print("[telegram] openai_warmup_ok")
        return

    print("[telegram] openai_warmup_failed continuing_without_circuit")
VALID_NEXT_ACTIONS = {
    "continuar_conversacion",
    "solicitar_segmento_cliente",
    "solicitar_clasificacion",
    "solicitar_tipo_cliente",
    "solicitar_nombre_razon_social",
    "solicitar_documento_verificacion",
    "solicitar_telefono_contacto",
    "solicitar_soporte_documental",
    "pendiente_aprobacion_humana",
    "solicitar_nif_o_nombre_fiscal",
    "solicitar_cliente_y_direccion",
    "confirmar_direccion_retiro",
    "solicitar_direccion_actualizada",
    "confirmar_programacion_ruta",
    "compartir_formulario_registro_cliente",
    "share_pqrs_link",
    "atender_otra_consulta",
}
CATALOG_QUERY_STOPWORDS = {
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "por",
    "para",
    "con",
    "sin",
    "que",
    "como",
    "cual",
    "cuales",
    "cuanto",
    "cuantos",
    "cuanta",
    "cuantas",
    "valor",
    "valores",
    "precio",
    "precios",
    "costo",
    "costos",
    "tarifa",
    "tarifas",
    "tipo",
    "tipos",
    "hacen",
    "hace",
    "ofrecen",
    "manejan",
    "tienen",
    "tiene",
    "servicios",
    "servicio",
    "analisis",
    "examen",
    "examenes",
    "prueba",
    "pruebas",
    "necesito",
    "quiero",
    "me",
    "ayudas",
    "ayuda",
    "favor",
    "porfa",
}
CATALOG_SAMPLE_GROUP_HINTS: dict[str, tuple[str, ...]] = {
    "sangre": (
        "sangre",
        "sanguineo",
        "sanguinea",
        "sanguineos",
        "sanguineas",
        "tubo",
        "suero",
        "plasma",
        "edta",
        "tapa roja",
        "tapa morada",
        "tapa azul",
        "tapa lila",
    ),
    "orina": ("orina", "urinaria", "urinario", "urinarias", "urinarios", "uroanal", "urocultivo"),
    "materia fecal": ("materia fecal", "copro", "heces"),
    "laminas/citologia": ("lamina", "laminas", "citologia", "paf", "frotis"),
    "piel y pelos": ("piel", "pelo", "pelos", "raspado", "acaro"),
    "secreciones": ("secrecion", "secreciones", "oido", "nasal", "vaginal"),
    "microbiologia/cultivo": (
        "cultivo",
        "antibiograma",
        "antifungigrama",
        "hemocultivo",
        "urocultivo",
        "hongos",
        "bacteria",
    ),
}
CATALOG_CLINICAL_GROUP_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "hematologia y hemostasia",
        (
            "hemograma",
            "hemoglobina",
            "hematocrito",
            "reticuloc",
            "plaqueta",
            "coombs",
            "protrombina",
            "tromboplastina",
            "fibrinog",
            "dimero",
            "coagul",
        ),
    ),
    (
        "bioquimica y metabolismo",
        (
            "alanino",
            "aspartato",
            "albumina",
            "amilasa",
            "bilirrub",
            "colesterol",
            "creatinina",
            "quinasa",
            "ldh",
            "fosfatasa",
            "fructosamina",
            "glucosa",
            "urea",
            "bun",
            "proteina",
            "globulina",
            "triglicer",
            "lipasa",
            "electrolitos",
            "sodio",
            "potasio",
            "cloro",
            "calcio",
            "fosforo",
            "magnesio",
            "acido urico",
            "gamma glutamil",
            "colinesterasa",
            "amonio",
        ),
    ),
    (
        "endocrinologia",
        ("t3", "t4", "tsh", "cortisol", "progesterona", "insulina", "tiroid", "estradiol"),
    ),
    (
        "parasitologia e infecciosas",
        (
            "copro",
            "parasito",
            "hemoparas",
            "ehrlich",
            "anaplas",
            "babesia",
            "leishmania",
            "giardia",
            "parvo",
            "corona",
            "distemper",
            "moquillo",
            "fiv",
            "felv",
            "toxoplas",
            "brucella",
            "leptosp",
            "calicivirus",
            "adenovirus",
            "panleucopenia",
            "dirofilaria",
            "trypanosoma",
        ),
    ),
    (
        "microbiologia y micologia",
        ("cultivo", "antibiograma", "antifungigrama", "micologico", "hongos", "bacteria"),
    ),
    (
        "citologia y patologia celular",
        ("citologia", "paf", "ascitico", "pleura", "nasal", "tvt", "malassezia", "sinovial"),
    ),
    (
        "inmunologia y serologia",
        ("anticuerpo", "antigeno", "inmunorreactiva", "elisa", "ifa", "serologia", "vcheck"),
    ),
)
PROFESSIONAL_AUDIENCE_TOKENS = {
    "hemograma",
    "hematocrito",
    "pt",
    "ptt",
    "fibrinogeno",
    "coprologico",
    "coproscopico",
    "urocultivo",
    "antibiograma",
    "paf",
    "cito",
    "perfil",
    "t4",
    "tsh",
    "sdma",
    "troponina",
    "resultados",
    "muestra",
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
        "enviar un examen al laboratorio",
        "enviar examenes al laboratorio",
        "mandar una prueba a analizar",
        "mandar prueba a analizar",
        "mandar unas pruebas",
        "mandar examen a analizar",
        "me recogen unos examenes",
        "remitir examenes",
        "tengo tubos y laminas para procesamiento",
        "tengo cosas para laboratorio",
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
        "como va el examen",
        "de mi paciente",
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
        "estado de muestra remitida",
        "vengo por estado de una muestra",
        "quiero ver si ya cerraron",
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
        "cuenta pendiente",
        "saldo pendiente",
        "pendientes contables",
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
        "vincular la clinica",
        "crear el perfil de mi clinica",
        "crear el perfil de la clinica",
        "perfil de mi clinica",
        "no estoy inscrito",
        "quiero empezar con ustedes",
        "abrir cuenta",
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
    "Hola, bienvenido a A3 laboratorio clinico veterinario.\n"
    "Para iniciar, cuentame si eres cliente nuevo o si ya trabajas con A3."
)
INITIAL_GREETING_MESSAGE_NO_QUESTION = (
    "Hola, bienvenido a A3 laboratorio clinico veterinario."
)
INTENT_CLARIFICATION_MESSAGE = (
    "Perfecto. Para avanzar rapido, dime si necesitas: programar recogida, consultar resultados, revisar pagos, PQRS u otra consulta."
)
ACCESS_SEGMENT_CLARIFICATION_MESSAGE = (
    "Para orientarte bien, confirmame si eres cliente nuevo o si ya eres cliente de A3."
)
PQRS_LINK_URL = "https://a3laboratorio.co/pqrs/"
PQRS_MESSAGE = (
    "Para PQRS, diligencia este enlace: "
    f"{PQRS_LINK_URL}"
)
OTHER_QUERIES_MESSAGE = (
    "Listo. Indica tu consulta y te respondo de forma puntual."
)
ROUTE_REMINDER_MESSAGE = (
    "Recordatorio: la Orden de Servicio debe estar completa al momento del retiro. "
    "Si aun no la tienes, te guiamos por chat para diligenciar los datos requeridos. "
    "Para procesamiento del mismo dia habil, registra la solicitud antes de las 5:30 PM."
)
NEW_CLIENT_REGISTRATION_MESSAGE = (
    "Registro de cliente nuevo. "
    "Este proceso se hace completamente por chat y requiere validacion humana. "
    "Para empezar, confirmame si actuas como clinica veterinaria o como medico veterinario independiente."
)
NEW_CLIENT_POST_REGISTRATION_MESSAGE = (
    "Gracias. Tu registro quedo en revision por el equipo de A3. "
    "Cuando sea aprobado, te habilitamos el flujo completo para solicitudes frecuentes."
)
NEW_CLIENT_POST_REGISTRATION_ROUTE_MESSAGE = (
    "Retomemos la programacion de ruta solicitada. "
    "Para continuar, comparteme tu NIF o el nombre fiscal de la veterinaria para ubicar tu registro."
)
ROUTE_CLIENT_IDENTIFICATION_MESSAGE = (
    "Para continuar con la ruta, "
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
            return "solicitar_tipo_cliente"
        if service_area == "unknown":
            return "atender_otra_consulta"
        return "continuar_conversacion"

    if "pqrs" in normalized:
        return "share_pqrs_link"
    if "segmento" in normalized or ("cliente" in normalized and "nuevo" in normalized):
        return "solicitar_segmento_cliente"
    if "tipo" in normalized and "cliente" in normalized:
        return "solicitar_tipo_cliente"
    if "razon social" in normalized or "nombre" in normalized:
        return "solicitar_nombre_razon_social"
    if "documento" in normalized and "verific" in normalized:
        return "solicitar_documento_verificacion"
    if "telefono" in normalized or "celular" in normalized:
        return "solicitar_telefono_contacto"
    if "adjunt" in normalized or "soporte" in normalized:
        return "solicitar_soporte_documental"
    if "aprobacion" in normalized:
        return "pendiente_aprobacion_humana"
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
        return "solicitar_tipo_cliente"
    if "continu" in normalized:
        return "continuar_conversacion"

    if service_area == "route_scheduling":
        if status in {"confirmed", "closed"}:
            return "continuar_conversacion"
        return "solicitar_cliente_y_direccion"
    if service_area == "new_client":
        return "solicitar_tipo_cliente"
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

    first_clause = re.split(r"\b(?:y luego|y despues|despues|luego)\b", normalized, maxsplit=1)[0].strip()
    if first_clause and first_clause != normalized:
        if any(token in first_clause for token in ("registr", "cliente nuevo", "primera vez", "alta", "abrir cuenta")):
            return "new_client"
        if any(token in first_clause for token in ("factura", "cartera", "saldo", "cuenta pendiente", "cobro")):
            return "accounting"
        if any(token in first_clause for token in ("resultado", "informe", "estado de muestra", "estado del resultado", "orden")):
            return "results"
        if any(token in first_clause for token in ("programar", "recogida", "retiro", "ruta", "enviar muestra", "recoleccion")):
            return "route_scheduling"

    normalized_lookup = normalize_lookup_key(text)
    catalog_like_markers = ("orina", "copro", "heces", "lamina", "citologia", "coombs", "creatinina")
    if (
        is_price_or_services_inquiry(text)
        and any(marker in normalized_lookup for marker in catalog_like_markers)
        and not any(marker in normalized_lookup for marker in ("resultado", "resultados", "informe", "orden"))
        and not is_route_operational_request(text)
    ):
        return None

    pattern_hits: dict[str, list[str]] = {
        service_area: [pattern for pattern in patterns if pattern in normalized]
        for service_area, patterns in EXPLICIT_INTENT_PATTERNS.items()
    }
    if any(pattern_hits.values()):
        if pattern_hits.get("new_client") and (
            "registr" in normalized or "primera vez" in normalized or "vincular" in normalized
        ):
            return "new_client"
        if pattern_hits.get("route_scheduling") and is_route_operational_request(text):
            return "route_scheduling"
        if "primera vez" in normalized and pattern_hits.get("new_client"):
            return "new_client"
        if (
            "cuenta pendiente" in normalized
            or "saldo pendiente" in normalized
            or ("factura" in normalized and "saldo" in normalized)
        ) and pattern_hits.get("accounting"):
            return "accounting"

        score_by_area: dict[str, int] = {}
        for service_area, hits in pattern_hits.items():
            if not hits:
                score_by_area[service_area] = 0
                continue
            longest = max(len(pattern) for pattern in hits)
            score = len(hits) * 10 + longest
            if service_area == "accounting" and any(
                token in normalized for token in ("factura", "cartera", "saldo", "pago", "cuenta")
            ):
                score += 12
            if service_area == "new_client" and any(
                token in normalized for token in ("registro", "registr", "primera vez", "alta", "nuevo")
            ):
                score += 12
            if service_area == "results" and any(
                token in normalized for token in ("resultado", "informe", "orden", "dictamen")
            ):
                score += 8
            score_by_area[service_area] = score

        ranked_hits = sorted(score_by_area.items(), key=lambda item: item[1], reverse=True)
        if ranked_hits and ranked_hits[0][1] > 0:
            return ranked_hits[0][0]

    tokens = extract_intent_tokens(normalized)
    if not tokens:
        return None

    results_tokens = {
        "resultado",
        "estad",
        "informe",
        "report",
        "diagnost",
        "list",
        "seguimiento",
        "trazabilidad",
        "dictamen",
        "lectura",
        "orden",
        "estudio",
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
        "material",
        "biologico",
        "pasen",
        "pasan",
    }
    route_action_tokens = {
        "mandar",
        "mando",
        "enviar",
        "envio",
        "analizar",
        "programar",
        "agendar",
        "retiro",
        "retirar",
        "recoger",
        "recogen",
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
        "lamina",
        "laminas",
        "tubo",
        "tubos",
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
    price_signal = is_price_or_services_inquiry(text)

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
    if has_sample_signal and has_route_action_signal and not price_signal:
        scores["route_scheduling"] += 3
    if "laboratorio" in tokens and (
        "enviar" in tokens or "envio" in tokens or "mandar" in tokens or "recogen" in tokens
    ) and not price_signal:
        scores["route_scheduling"] += 3

    if has_results_signal:
        scores["results"] += 4
    if has_results_signal and has_sample_signal and not has_route_direct_signal:
        scores["results"] += 2
    if has_accounting_signal:
        scores["accounting"] += 4
    if "cuenta" in tokens and ("pendiente" in tokens or "saldo" in tokens):
        scores["accounting"] += 3
        scores["results"] -= 1
    if has_new_client_signal:
        scores["new_client"] += 4
    if ("habilitar" in tokens or "aliado" in tokens or "primera" in tokens) and has_new_client_signal:
        scores["new_client"] += 3
        scores["accounting"] -= 2
    if "cuenta" in tokens and has_new_client_signal:
        scores["new_client"] += 2
    if "primera" in tokens and "vez" in tokens:
        scores["new_client"] += 4
        scores["results"] -= 2

    if has_new_client_signal and has_route_action_signal:
        scores["route_scheduling"] += 2
        scores["new_client"] -= 1
    if has_results_signal and has_route_action_signal and has_sample_signal:
        scores["route_scheduling"] += 2
    if has_results_signal and not has_route_action_signal and not has_route_direct_signal:
        scores["route_scheduling"] -= 2
    if has_new_client_signal and not has_route_direct_signal:
        scores["route_scheduling"] -= 2
    if "pasen" in tokens and has_sample_signal:
        scores["route_scheduling"] += 2
    if "pasan" in tokens and has_sample_signal:
        scores["route_scheduling"] += 2
    if "vet" in tokens and has_route_action_signal and not price_signal:
        scores["route_scheduling"] += 1

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

    match = re.fullmatch(r"([1-5])[\).]?", normalized)
    if not match:
        return None

    return {
        "1": "route_scheduling",
        "2": "results",
        "3": "accounting",
        "4": "pqrs",
        "5": "other_queries",
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


def detect_access_segment_option(text: str) -> str | None:
    normalized = normalize_text_value(text)
    if not normalized:
        return None

    if re.fullmatch(r"1[\).]?", normalized):
        return "new_client"
    if re.fullmatch(r"2[\).]?", normalized):
        return "existing_client"

    if any(token in normalized for token in ("cliente nuevo", "primera vez", "nuevo cliente")):
        return "new_client"
    if any(token in normalized for token in ("ya soy cliente", "cliente frecuente", "cliente actual")):
        return "existing_client"

    return None


def parse_new_client_profile_type(text: str) -> str | None:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return None

    clinic_markers = (
        "clinica veterinaria",
        "tengo clinica",
        "somos clinica",
        "clinica",
        "veterinaria",
        "empresa",
    )
    independent_markers = (
        "medico veterinario independiente",
        "veterinario independiente",
        "medico veterinario",
        "doctor veterinario",
        "soy veterinario",
        "soy medico veterinario",
        "independiente",
        "mvz",
    )

    if any(token in normalized for token in clinic_markers):
        return "clinica"
    if any(token in normalized for token in independent_markers):
        return "medico_independiente"
    return None


def is_new_client_onboarding_locked(
    *,
    session: dict[str, Any] | None,
    session_service_area: str,
    service_area: str,
    requires_handoff: bool,
) -> bool:
    if requires_handoff:
        return False

    current_area = service_area or session_service_area
    if current_area != "new_client":
        return False

    if not session:
        return service_area == "new_client"

    status = str((session or {}).get("status") or "").strip().lower()
    if status in {"closed", "confirmed", "approved_manual", "rejected_manual"}:
        return False

    active_actions = {
        "solicitar_tipo_cliente",
        "solicitar_nombre_razon_social",
        "solicitar_documento_verificacion",
        "solicitar_telefono_contacto",
        "solicitar_soporte_documental",
        "pendiente_aprobacion_humana",
    }
    next_action = str((session or {}).get("next_action") or "").strip().lower()
    return next_action in active_actions or service_area == "new_client"


def is_non_eligible_final_consumer(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    risky_tokens = (
        "soy propietario",
        "dueno de mascota",
        "dueño de mascota",
        "mi mascota",
        "mi perro",
        "mi gato",
        "soy particular",
        "cliente final",
    )
    return any(token in normalized for token in risky_tokens)


def user_requests_flow_exit(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    exit_markers = (
        "cancelar",
        "salir",
        "volver al menu",
        "menu",
        "cambiar tema",
        "otro tema",
        "dejemos esto",
        "no quiero registrarme",
    )
    return any(marker in normalized for marker in exit_markers)


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
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    direct_tokens = (
        "cuanto",
        "precio",
        "precios",
        "costos",
        "costo",
        "tarifa",
        "tarifas",
        "valor",
        "valores",
        "cuanto sale",
        "cuanto salen",
        "sale",
        "salen",
        "que servicios",
        "servicios tienen",
        "tipo de analisis",
        "que tipo de analisis",
        "que examenes",
        "que examen",
    )
    if any(token in normalized for token in direct_tokens):
        if "resultado" in normalized and not any(
            token in normalized
            for token in (
                "analisis",
                "examen",
                "servicio",
                "precio",
                "valor",
                "tarifa",
            )
        ):
            return False
        return True

    if "consulta sobre" in normalized and any(
        token in normalized for token in ("analisis", "examen", "servicio")
    ):
        return True

    if (
        any(token in normalized for token in ("hacen", "manejan", "ofrecen"))
        and any(token in normalized for token in ("analisis", "examen"))
    ):
        return True

    return False


def normalized_word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_lookup_key(text))


def contains_normalized_hint(normalized: str, tokens: list[str], hint: str) -> bool:
    normalized_hint = normalize_lookup_key(hint)
    if not normalized_hint:
        return False
    if " " in normalized_hint:
        return normalized_hint in normalized

    for token in tokens:
        if token == normalized_hint:
            return True
        if len(normalized_hint) >= 6 and token.startswith(normalized_hint):
            return True
    return False


def is_route_operational_request(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    if is_price_or_services_inquiry(text):
        explicit_route_markers = (
            "programar",
            "agendar",
            "retiro",
            "recoger",
            "recoleccion",
            "ruta",
            "mensajero",
            "motorizado",
        )
        if not any(marker in normalized for marker in explicit_route_markers):
            sample_markers = ("orina", "copro", "heces", "lamina", "citologia", "coombs", "creatinina")
            if any(marker in normalized for marker in sample_markers):
                return False

    route_patterns = (
        "programar recogida",
        "programar recoleccion",
        "agendar retiro",
        "programacion de ruta",
        "recoger muestra",
        "retiro de muestra",
        "enviar muestra",
        "enviar muestras",
        "mandar a analizar una muestra",
        "mandar una prueba a analizar",
        "mandar examen a analizar",
        "enviar un examen al laboratorio",
        "enviar examen al laboratorio",
        "me recogen unos examenes",
        "remitir examenes",
        "tengo tubos y laminas para procesamiento",
        "tengo cosas para laboratorio",
        "procesar un panel diagnostico",
        "procesar panel diagnostico",
        "procesar muestra",
        "ruta",
    )
    return any(pattern in normalized for pattern in route_patterns)


def is_catalog_inquiry(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    if is_route_operational_request(text):
        return False

    tokens = normalized_word_tokens(text)

    if is_price_or_services_inquiry(text):
        return True

    if infer_requested_sample_groups(text) or infer_requested_clinical_groups(text):
        return True

    broad_tokens = (
        "analisis",
        "examen",
        "examenes",
        "prueba",
        "pruebas",
        "perfil",
        "panel",
        "citologia",
        "copro",
        "coprolog",
        "coproscop",
        "orina",
        "urin",
        "sangre",
        "heces",
        "lamina",
        "laminas",
        "paf",
        "urocultivo",
        "coombs",
        "creatinina",
        "hemograma",
    )
    return any(contains_normalized_hint(normalized, tokens, hint) for hint in broad_tokens)


def format_price_cop(value: Any) -> str:
    try:
        amount = int(float(str(value)))
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    return f"${amount:,}".replace(",", ".") + " COP"


def format_turnaround_for_reply(row: dict[str, Any]) -> str:
    subcategory = str(row.get("subcategory") or "").strip()
    if subcategory:
        return subcategory

    hours_raw = row.get("turnaround_hours")
    try:
        hours = int(float(str(hours_raw)))
    except (TypeError, ValueError):
        return ""

    if hours <= 0:
        return ""
    if hours % 24 == 0:
        days = hours // 24
        return f"{days} dia(s)"
    return f"{hours} hora(s)"


def format_route_pickup_date_label(date_iso: str | None) -> str:
    if not date_iso:
        return ""

    try:
        pickup_date = datetime.fromisoformat(str(date_iso))
    except ValueError:
        return ""

    weekdays = [
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
    ]
    months = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    weekday = weekdays[pickup_date.weekday()]
    month = months[pickup_date.month - 1]
    return f"{weekday} {pickup_date.day} de {month} de {pickup_date.year}"


def catalog_blob_with_context(row: dict[str, Any]) -> str:
    return normalize_lookup_key(
        " ".join(
            [
                str(row.get("test_name") or ""),
                str(row.get("category") or ""),
                str(row.get("subcategory") or ""),
                str(row.get("sample_type") or ""),
            ]
        )
    )


def infer_catalog_sample_group(row: dict[str, Any]) -> str:
    blob = catalog_blob_with_context(row)
    if not blob:
        return "no especificado"

    for group, hints in CATALOG_SAMPLE_GROUP_HINTS.items():
        if any(hint in blob for hint in hints):
            return group

    return "no especificado"


def infer_catalog_clinical_group(row: dict[str, Any]) -> str:
    blob = catalog_blob_with_context(row)
    if not blob:
        return "otros analisis"

    for group, hints in CATALOG_CLINICAL_GROUP_RULES:
        if any(hint in blob for hint in hints):
            return group

    return "otros analisis"


def infer_catalog_collection_note(row: dict[str, Any]) -> str:
    blob = catalog_blob_with_context(row)
    if not blob:
        return ""

    if "orina" in blob and "esteril" in blob:
        return "orina fresca y esteril"
    if "orina" in blob:
        return "orina fresca"
    if "materia fecal" in blob:
        return "materia fecal fresca"
    if "lamina" in blob and "enviar" in blob:
        return "laminas para evaluacion citologica"
    if "lamina" in blob:
        return "laminas citologicas"
    if "piel" in blob and "pelo" in blob:
        return "muestra de piel y pelos"
    if "tapa morada" in blob and "tapa roja" in blob:
        return "sangre en tubo tapa morada y tapa roja"
    if "tapa azul" in blob:
        return "sangre en tubo tapa azul"
    if "tapa morada" in blob:
        return "sangre en tubo tapa morada"
    if "tapa roja" in blob or "tubo rojo" in blob:
        return "sangre en tubo tapa roja"
    if "tapa lila" in blob:
        return "sangre en tubo tapa lila"
    if "suero" in blob:
        return "suero"
    if "sangre" in blob or "tubo" in blob:
        return "muestra sanguinea"
    if "cultivo" in blob:
        return "muestra segun sitio de infeccion y medio adecuado"

    explicit_sample_type = str(row.get("sample_type") or "").strip()
    if explicit_sample_type:
        return explicit_sample_type

    return ""


def detect_catalog_audience(text: str) -> str:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return "general"

    if any(token in normalized for token in PROFESSIONAL_AUDIENCE_TOKENS):
        return "profesional"
    return "general"


def infer_requested_sample_groups(text: str) -> set[str]:
    normalized = normalize_lookup_key(text)
    tokens = normalized_word_tokens(text)
    requested: set[str] = set()
    for group, hints in CATALOG_SAMPLE_GROUP_HINTS.items():
        if any(contains_normalized_hint(normalized, tokens, hint) for hint in hints):
            requested.add(group)
    return requested


def infer_requested_clinical_groups(text: str) -> set[str]:
    normalized = normalize_lookup_key(text)
    tokens = normalized_word_tokens(text)
    requested: set[str] = set()
    for group, hints in CATALOG_CLINICAL_GROUP_RULES:
        if any(contains_normalized_hint(normalized, tokens, hint) for hint in hints):
            requested.add(group)
    return requested


def enrich_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    enriched["clinical_group"] = infer_catalog_clinical_group(row)
    enriched["sample_group"] = infer_catalog_sample_group(row)
    enriched["collection_note"] = infer_catalog_collection_note(row)
    return enriched


def build_catalog_exam_reply(best: dict[str, Any], *, audience: str, wants_price: bool) -> str:
    test_name = str(best.get("test_name") or "este analisis").strip()
    code = str(best.get("test_code") or "").strip()
    price_label = format_price_cop(best.get("price_cop"))
    turnaround_label = format_turnaround_for_reply(best)
    sample_group = str(best.get("sample_group") or "no especificado").strip()
    collection_note = str(best.get("collection_note") or "").strip()
    clinical_group = str(best.get("clinical_group") or "otros analisis").strip()

    prefix = "Listo" if audience == "profesional" else "Entendido"
    exam_label = f"{test_name} (codigo {code})" if code else test_name
    response_parts = [f"{prefix}, para {exam_label} del grupo {clinical_group}"]

    if sample_group != "no especificado":
        response_parts.append(f"la muestra base es {sample_group}")
    if collection_note:
        response_parts.append(f"la toma recomendada es {collection_note}")
    if price_label and wants_price:
        response_parts.append(f"el valor referencial es {price_label}")
    elif not wants_price and price_label:
        response_parts.append(f"valor referencial: {price_label}")
    if turnaround_label:
        response_parts.append(f"y el tiempo estimado es {turnaround_label}")

    message = ", ".join(response_parts).strip() + "."
    if audience == "profesional":
        return f"{message} Si lo requieres, te paso alternativas del mismo grupo diagnostico."
    return f"{message} Si lo requieres, te indico alternativas del mismo grupo."


def build_catalog_group_reply(
    catalog_rows: list[dict[str, Any]],
    *,
    requested_samples: set[str],
    requested_clinical_groups: set[str],
    audience: str,
) -> str | None:
    filtered = catalog_rows
    if requested_samples:
        filtered = [row for row in filtered if row.get("sample_group") in requested_samples]
    if requested_clinical_groups:
        filtered = [row for row in filtered if row.get("clinical_group") in requested_clinical_groups]

    if not filtered:
        return None

    unique_names: list[str] = []
    for row in filtered:
        name = str(row.get("test_name") or "").strip()
        if name and name not in unique_names:
            unique_names.append(name)
        if len(unique_names) >= 3:
            break

    price_values = [
        int(value)
        for value in [row.get("price_cop") for row in filtered]
        if isinstance(value, int) and value > 0
    ]
    min_price = min(price_values) if price_values else None
    max_price = max(price_values) if price_values else None
    sample_label = ", ".join(sorted(requested_samples)) if requested_samples else "distintas muestras"

    if requested_clinical_groups:
        group_label = ", ".join(sorted(requested_clinical_groups))
    else:
        top_groups = Counter(str(row.get("clinical_group") or "otros analisis") for row in filtered)
        group_label = ", ".join(group for group, _ in top_groups.most_common(2))

    top_turnaround = Counter(str(row.get("subcategory") or "").strip() for row in filtered if str(row.get("subcategory") or "").strip())
    turnaround_label = top_turnaround.most_common(1)[0][0] if top_turnaround else "segun el examen"

    examples_label = " y ".join(unique_names[:2]) if unique_names else "varios examenes"
    if min_price and max_price:
        price_span = f"entre {format_price_cop(min_price)} y {format_price_cop(max_price)}"
    else:
        price_span = "con valores referenciales segun examen"

    if audience == "profesional":
        return (
            f"Catalogo disponible para {sample_label} con pruebas en {group_label}, {price_span}. "
            f"Por ejemplo, {examples_label}, con tiempo estimado de referencia {turnaround_label}. "
            "Indica objetivo clinico y te priorizo el panel mas util."
        )

    return (
        f"Catalogo disponible para {sample_label} con examenes de {group_label}, {price_span}. "
        f"Por ejemplo, {examples_label}, con tiempo estimado de referencia {turnaround_label}. "
        "Indica examen o codigo y te doy valor referencial y toma de muestra."
    )


def catalog_query_tokens(text: str) -> set[str]:
    normalized = normalize_lookup_key(text)
    raw_tokens = re.findall(r"[a-z0-9]+", normalized)
    tokens = {
        token
        for token in raw_tokens
        if len(token) >= 3 and token not in CATALOG_QUERY_STOPWORDS
    }
    return tokens


def catalog_row_search_blob(row: dict[str, Any]) -> str:
    return normalize_lookup_key(
        " ".join(
            [
                str(row.get("test_code") or ""),
                str(row.get("test_name") or ""),
                str(row.get("category") or ""),
                str(row.get("subcategory") or ""),
                str(row.get("sample_type") or ""),
            ]
        )
    )


def rank_catalog_matches(text: str, catalog_rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    normalized = normalize_lookup_key(text)
    query_tokens = catalog_query_tokens(text)
    ranked: list[tuple[int, dict[str, Any]]] = []

    for row in catalog_rows:
        blob = catalog_row_search_blob(row)
        if not blob:
            continue

        code = normalize_lookup_key(str(row.get("test_code") or ""))
        name = normalize_lookup_key(str(row.get("test_name") or ""))
        row_tokens = {token for token in re.findall(r"[a-z0-9]+", blob) if len(token) >= 3}

        score = 0
        if code and code in normalized:
            score += 12
        if name and len(name) >= 5 and name in normalized:
            score += 8

        overlap = len(query_tokens & row_tokens)
        score += overlap * 3

        if query_tokens and query_tokens.issubset(row_tokens):
            score += 3

        if score > 0:
            ranked.append((score, row))

    ranked.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("test_name") or "").lower(),
        ),
        reverse=True,
    )
    return ranked


def build_catalog_guidance_reply(text: str) -> str | None:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return None

    requested_samples = infer_requested_sample_groups(text)
    requested_clinical_groups = infer_requested_clinical_groups(text)

    inquiry_detected = is_catalog_inquiry(text)
    if requested_samples or requested_clinical_groups:
        inquiry_detected = True
    if not inquiry_detected:
        return None

    list_catalog = getattr(supabase, "list_catalog_tests", None)
    if not callable(list_catalog):
        return None

    try:
        raw_catalog = list_catalog(limit=4000)
    except httpx.HTTPStatusError:
        return None

    catalog_rows = [
        enrich_catalog_row(row)
        for row in ensure_dict_rows(raw_catalog)
        if row and row.get("is_active") is not False
    ]
    if not catalog_rows:
        return (
            "No tengo el catalogo detallado cargado en este momento. "
            "Indica examen o perfil y te doy orientacion puntual."
        )

    ranked = rank_catalog_matches(text, catalog_rows)
    audience = detect_catalog_audience(text)
    wants_price = any(
        token in normalized
        for token in (
            "precio",
            "precios",
            "valor",
            "valores",
            "costo",
            "costos",
            "tarifa",
            "tarifas",
            "cuanto",
            "cuanto sale",
            "cuanto cuesta",
        )
    )

    if ranked and ranked[0][0] >= 3:
        best = ranked[0][1]
        return build_catalog_exam_reply(best, audience=audience, wants_price=wants_price)

    grouped_reply = build_catalog_group_reply(
        catalog_rows,
        requested_samples=requested_samples,
        requested_clinical_groups=requested_clinical_groups,
        audience=audience,
    )
    if grouped_reply:
        if wants_price and not requested_samples and not requested_clinical_groups:
            return f"{grouped_reply} Para precio puntual, comparte nombre exacto o codigo del examen."
        return grouped_reply

    category_counter: Counter[str] = Counter()
    for row in catalog_rows:
        category = str(row.get("clinical_group") or "otros analisis").strip()
        if category:
            category_counter[category] += 1

    top_categories = [name for name, _count in category_counter.most_common(4)]
    category_label = ", ".join(top_categories) if top_categories else "distintos tipos de examenes"

    suggestions = [
        str(row.get("test_name") or "").strip()
        for _score, row in ranked[:2]
        if str(row.get("test_name") or "").strip()
    ]
    if len(suggestions) < 2:
        for row in catalog_rows[:5]:
            name = str(row.get("test_name") or "").strip()
            if name and name not in suggestions:
                suggestions.append(name)
            if len(suggestions) >= 2:
                break

    if suggestions:
        sample_label = " y ".join(suggestions[:2])
        return (
            f"Catalogo disponible en {category_label}. "
            f"Ejemplos: {sample_label}. Indica examen exacto o tipo de muestra y te paso valor referencial, toma y tiempo estimado."
        )

    return (
        "Puedo orientarte con catalogo y tiempos. "
        "Indica examen exacto o codigo y te paso valor referencial en COP y tiempo estimado."
    )


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

    clinic_candidate: str | None = None
    address_candidate: str | None = None

    clinic_match = re.search(
        r"(?:veterinaria|clinica)\s*(?:es|:)?\s*([A-Za-z0-9ÁÉÍÓÚáéíóúÑñ .'-]{3,}?)(?=(?:\s+y\s+la\s+direcci[oó]n|\s*,|$))",
        raw,
        flags=re.IGNORECASE,
    )
    if clinic_match:
        clinic_candidate = clinic_match.group(1).strip(" .,-")

    address_match = re.search(
        r"(?:direccion|dirección)\s*(?:de retiro|de recogida|es|:)?\s*([A-Za-z0-9ÁÉÍÓÚáéíóúÑñ# .,'-]{6,})",
        raw,
        flags=re.IGNORECASE,
    )
    if address_match:
        address_candidate = address_match.group(1).strip(" .,-")
        if isinstance(address_candidate, str) and address_candidate.lower().startswith("es "):
            address_candidate = address_candidate[3:].strip()

    if clinic_candidate or address_candidate:
        return clinic_candidate or None, address_candidate or None

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) >= 2:
        clinic_candidate = parts[0]
        address_candidate = ", ".join(parts[1:])
        return clinic_candidate or None, address_candidate or None

    has_digit = any(char.isdigit() for char in raw)
    if has_digit:
        return None, raw

    return raw, None


def detect_route_priority(text: str, captured_fields: dict[str, Any]) -> str:
    existing = str(captured_fields.get("priority") or "").strip().lower()
    if existing in {"urgent", "normal"}:
        return existing

    normalized = normalize_lookup_key(text)
    if not normalized:
        return "normal"

    urgent_tokens = (
        "urgente",
        "prioridad alta",
        "lo antes posible",
        "ya mismo",
        "inmediato",
        "hoy mismo",
        "asap",
    )
    if any(token in normalized for token in urgent_tokens):
        return "urgent"

    return "normal"


def detect_route_time_window(text: str, captured_fields: dict[str, Any]) -> str | None:
    existing = str(captured_fields.get("pickup_time_window") or "").strip()
    if existing:
        return existing

    normalized = normalize_lookup_key(text)
    if not normalized:
        return None

    between_hours = re.search(
        r"entre\s+las?\s*(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\s+y\s+las?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        normalized,
    )
    if between_hours:
        start_hour = between_hours.group(1)
        start_min = between_hours.group(2) or "00"
        end_hour = between_hours.group(3)
        end_min = between_hours.group(4) or "00"
        meridiem = between_hours.group(5) or ""
        suffix = f" {meridiem}" if meridiem else ""
        return f"entre {start_hour}:{start_min} y {end_hour}:{end_min}{suffix}".strip()

    colloquial_ranges = (
        ("manana", "jornada de manana"),
        ("tarde", "jornada de la tarde"),
        ("noche", "jornada de la noche"),
    )
    for token, label in colloquial_ranges:
        if token in normalized:
            return label

    after_hour = re.search(r"despues\s+de\s+las?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized)
    if after_hour:
        hour = after_hour.group(1)
        minute = after_hour.group(2) or "00"
        meridiem = after_hour.group(3) or ""
        suffix = f" {meridiem}" if meridiem else ""
        return f"despues de las {hour}:{minute}{suffix}".strip()

    return None

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
        r"^\s*(.+?)\s+es\s+mi\s+veterinaria\b.*$",
        r"^\s*(?:si\s+)?(?:estoy\s+)?(?:registrad[oa]\s*,?\s*)?(.+?)\s+se\s+llama\s+mi\s+veterinaria\b.*$",
        r"^\s*(?:perdon\w*\s+)?(?:me\s+equivoqu[eé]\s+)?se\s+llama\s+(.+?)\s*$",
        r"^\s*(?:mi\s+)?veterinaria\s+se\s+llama\s+(.+?)\s*$",
        r"^\s*(?:mi\s+)?clinica\s+se\s+llama\s+(.+?)\s*$",
        r"^\s*(?:la\s+)?veterinaria\s+es\s+(.+?)\s*$",
        r"^\s*(?:la\s+)?clinica\s+es\s+(.+?)\s*$",
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
        "priority": str(captured_fields.get("priority") or "normal"),
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


def get_message_from_update(update: dict[str, Any]) -> tuple[int, str, bool]:
    message = update.get("message") or update.get("edited_message")
    if not message:
        raise ValueError("No message payload")

    chat = message.get("chat", {})
    text = message.get("text") or message.get("caption") or ""
    has_attachment = bool(message.get("photo") or message.get("document") or message.get("image"))
    chat_id = chat.get("id")

    if chat_id is None:
        raise ValueError("Missing chat id")

    return int(chat_id), text, has_attachment


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


def build_pending_approval_rows(session_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in session_rows:
        captured = item.get("captured_fields") if isinstance(item.get("captured_fields"), dict) else {}
        review_status = str(captured.get("new_client_review_status") or "").strip().lower()
        if review_status != "pending_manual_approval":
            continue

        client_data = item.get("clients") if isinstance(item.get("clients"), dict) else {}
        profile_type = str(captured.get("new_client_profile_type") or "").strip()
        profile_label = (
            "Clinica veterinaria"
            if profile_type == "clinica"
            else "Medico veterinario independiente"
        )
        rows.append(
            {
                "external_chat_id": str(item.get("external_chat_id") or "-"),
                "clinic_name": str(
                    captured.get("new_client_legal_name")
                    or client_data.get("clinic_name")
                    or "Sin nombre"
                ),
                "profile_type": profile_type,
                "profile_label": profile_label,
                "document_type": str(captured.get("new_client_document_type") or "-").replace("_", " "),
                "document_number": str(captured.get("new_client_document_number") or "-"),
                "contact_phone": str(captured.get("new_client_contact_phone") or client_data.get("phone") or "-"),
                "updated_at": str(item.get("updated_at") or "-"),
                "request_id": str(item.get("request_id") or ""),
            }
        )

    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return rows


def build_reviewed_approval_rows(session_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in session_rows:
        captured = item.get("captured_fields") if isinstance(item.get("captured_fields"), dict) else {}
        review_status = str(captured.get("new_client_review_status") or "").strip().lower()
        if review_status not in {"approved_manual", "rejected_manual"}:
            continue

        client_data = item.get("clients") if isinstance(item.get("clients"), dict) else {}
        rows.append(
            {
                "external_chat_id": str(item.get("external_chat_id") or "-"),
                "clinic_name": str(
                    captured.get("new_client_legal_name")
                    or client_data.get("clinic_name")
                    or "Sin nombre"
                ),
                "review_status": review_status,
                "review_status_label": "Aprobado" if review_status == "approved_manual" else "Rechazado",
                "review_by": str(captured.get("new_client_review_by") or "-"),
                "review_at": str(captured.get("new_client_review_at") or item.get("updated_at") or "-"),
                "review_reason": str(captured.get("new_client_review_reason") or "-"),
            }
        )

    rows.sort(key=lambda row: row.get("review_at") or "", reverse=True)
    return rows[:120]


def filter_pending_approval_rows(
    rows: list[dict[str, Any]],
    *,
    query: str,
    profile_type: str,
    since_date: str,
) -> list[dict[str, Any]]:
    normalized_query = normalize_lookup_key(query)
    normalized_profile = normalize_lookup_key(profile_type)
    normalized_since = (since_date or "").strip()

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if normalized_profile and normalized_profile not in {"all", "todos"}:
            if normalize_lookup_key(str(row.get("profile_type") or "")) != normalized_profile:
                continue

        if normalized_query:
            blob = normalize_lookup_key(
                " ".join(
                    [
                        str(row.get("clinic_name") or ""),
                        str(row.get("document_number") or ""),
                        str(row.get("contact_phone") or ""),
                        str(row.get("external_chat_id") or ""),
                    ]
                )
            )
            if normalized_query not in blob:
                continue

        if normalized_since:
            row_date = str(row.get("updated_at") or "")[:10]
            if row_date and row_date < normalized_since:
                continue

        filtered.append(row)

    return filtered


def build_affiliation_rows(
    professionals_rows: list[dict[str, Any]],
    clinic_name_by_key: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in professionals_rows:
        clinic_key = str(item.get("clinic_key") or "").strip()
        professional_name = str(item.get("professional_name") or "").strip()
        professional_card = str(item.get("professional_card") or "").strip()
        if not clinic_key or not professional_name:
            continue

        professional_key = str(item.get("professional_key") or "").strip()
        if not professional_key:
            professional_key = normalize_lookup_key(f"{professional_name}|{professional_card}")

        rows.append(
            {
                "clinic_key": clinic_key,
                "clinic_name": clinic_name_by_key.get(clinic_key, clinic_key),
                "professional_key": professional_key,
                "professional_name": professional_name,
                "professional_card": professional_card or "-",
                "source_sheet": str(item.get("source_sheet") or "manual"),
            }
        )

    rows.sort(
        key=lambda row: (
            str(row.get("clinic_name") or "").lower(),
            str(row.get("professional_name") or "").lower(),
        )
    )
    return rows


def build_dashboard_context() -> dict[str, Any]:
    if settings.dashboard_data_mode == "mock":
        return load_mock_dashboard_context()

    clients = safe_fetch(supabase.list_clients_with_assignment, [])
    requests_rows = safe_fetch(lambda: supabase.list_requests(limit=4000), [])
    conversations = safe_fetch(lambda: supabase.list_recent_conversations(limit=300), [])
    messages = safe_fetch(lambda: supabase.list_recent_messages(limit=500), [])
    catalog = safe_fetch(lambda: supabase.list_catalog_tests(limit=4000), [])
    flow_sessions = safe_fetch(lambda: supabase.list_telegram_sessions_with_client(limit=3000), [])
    approval_sessions = safe_fetch(
        lambda: supabase.fetch_rows(
            "telegram_sessions",
            {
                "select": "external_chat_id,request_id,updated_at,captured_fields,clients(clinic_name,phone)",
                "order": "updated_at.desc",
                "limit": "3000",
            },
        ),
        [],
    )
    knowledge_rows = safe_fetch(
        lambda: supabase.fetch_rows(
            "clients_a3_knowledge",
            {
                "select": "clinic_key,clinic_name",
                "order": "clinic_name.asc",
                "limit": "4000",
            },
        ),
        [],
    )
    professionals_rows = safe_fetch(
        lambda: supabase.fetch_rows(
            "clients_a3_professionals",
            {
                "select": "clinic_key,professional_key,professional_name,professional_card,source_sheet",
                "order": "clinic_key.asc",
                "limit": "6000",
            },
        ),
        [],
    )
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

    approval_rows = build_pending_approval_rows(approval_sessions)
    reviewed_approval_rows = build_reviewed_approval_rows(approval_sessions)
    clinic_name_by_key = {
        str(row.get("clinic_key") or "").strip(): str(row.get("clinic_name") or "").strip()
        for row in ensure_dict_rows(knowledge_rows)
        if str(row.get("clinic_key") or "").strip()
    }
    affiliation_rows = build_affiliation_rows(ensure_dict_rows(professionals_rows), clinic_name_by_key)
    summary_cards["pending_manual_approvals"] = len(approval_rows)
    summary_cards["reviewed_manual_approvals"] = len(reviewed_approval_rows)
    summary_cards["clinic_professionals"] = len(affiliation_rows)

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
        "approval_rows": approval_rows,
        "reviewed_approval_rows": reviewed_approval_rows,
        "affiliation_rows": affiliation_rows,
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


def is_low_information_reply(reply: str) -> bool:
    normalized = normalize_lookup_key(reply)
    if not normalized:
        return True
    generic_patterns = (
        "entiendo te ayudo con gusto",
        "gracias te ayudo con eso",
        "perfecto te ayudo con eso",
        "claro te ayudo con eso",
    )
    return len(normalized) < 45 or any(pattern in normalized for pattern in generic_patterns)


def enforce_service_area_reply_quality(
    *,
    service_area: str,
    reply: str,
    missing_fields: list[str],
) -> str:
    if not is_low_information_reply(reply):
        return reply

    if service_area == "results":
        return (
            "Perfecto, te ayudo con resultados. Para darte el estado puntual, "
            "comparteme numero de muestra, numero de orden o nombre de la mascota."
        )
    if service_area == "accounting":
        resume_prompt = build_resume_question(missing_fields)
        if resume_prompt:
            return f"Perfecto, te ayudo con contabilidad. {resume_prompt}"
        return (
            "Perfecto, te ayudo con contabilidad. Para revisarlo rapido, "
            "comparteme NIF y si tienes numero de factura o periodo de cobro."
        )
    if service_area == "new_client":
        return NEW_CLIENT_REGISTRATION_MESSAGE
    if service_area == "route_scheduling" and missing_fields:
        resume_prompt = build_resume_question(missing_fields)
        if resume_prompt:
            return (
                "Perfecto, te apoyo con la programacion de ruta. "
                f"{resume_prompt}"
            )
    if service_area == "unknown":
        resume_prompt = build_resume_question(missing_fields)
        if resume_prompt:
            return f"Para ayudarte mejor, {resume_prompt}"
        return INTENT_CLARIFICATION_MESSAGE
    return reply


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

    if "orden de servicio" in normalize_lookup_key(base_message):
        return base_message

    return f"{base_message}\n\n{ROUTE_REMINDER_MESSAGE}"


def should_share_new_client_registration(
    *,
    service_area: str,
    requires_handoff: bool,
    reply: str,
    next_action: str,
) -> bool:
    if requires_handoff:
        return False

    if service_area != "new_client":
        return False

    if next_action != "compartir_formulario_registro_cliente":
        return False

    return reply not in {INTENT_CLARIFICATION_MESSAGE, ACCESS_SEGMENT_CLARIFICATION_MESSAGE}


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
    pickup_time_window = str(captured_fields.get("pickup_time_window") or "").strip()
    if clinic_name:
        captured_fields["clinic_name"] = clinic_name
    if pickup_address:
        captured_fields["pickup_address"] = pickup_address
    detected_time_window = detect_route_time_window(text, captured_fields)
    if detected_time_window:
        captured_fields["pickup_time_window"] = detected_time_window
        pickup_time_window = detected_time_window

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
        normalized_lookup = normalize_lookup_key(text)
        if "habitual" in normalized_lookup:
            text = "si"
        elif "nueva" in normalized_lookup:
            text = "no"

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
        if not pickup_time_window:
            pickup_time_window = str(captured_fields.get("pickup_time_window") or "").strip()

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


def apply_new_client_onboarding_guard(
    *,
    text: str,
    captured_fields: dict[str, Any],
    has_attachment: bool,
) -> tuple[str, str, str, str, list[str], dict[str, Any], str, bool, str]:
    captured_fields["active_mission"] = "new_client_registration"
    profile_type = str(captured_fields.get("new_client_profile_type") or "").strip().lower()
    if not profile_type:
        detected_profile = parse_new_client_profile_type(text)
        if detected_profile:
            profile_type = detected_profile
            captured_fields["new_client_profile_type"] = profile_type

    if not profile_type:
        if detect_access_segment_option(text) == "new_client":
            captured_fields["mission_step"] = "tipo_cliente"
            return (
                "fase_2_recogida_datos",
                "fase_3_validacion",
                "in_progress",
                "solicitar_tipo_cliente",
                ["tipo de cliente profesional"],
                captured_fields,
                "Perfecto. Para continuar el registro, cuentame si trabajas como clinica veterinaria o como medico veterinario independiente.",
                False,
                "none",
            )
        captured_fields["mission_step"] = "tipo_cliente"
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "solicitar_tipo_cliente",
            ["tipo de cliente profesional"],
            captured_fields,
            "Para continuar el registro, indicame si eres clinica veterinaria o medico veterinario independiente.",
            False,
            "none",
        )

    legal_name = str(captured_fields.get("new_client_legal_name") or "").strip()
    if not legal_name:
        candidate_name = extract_clinic_name_hint(text)
        if candidate_name and len(candidate_name) >= 4:
            legal_name = candidate_name
            captured_fields["new_client_legal_name"] = legal_name

    if not legal_name:
        label = "razon social de la clinica" if profile_type == "clinica" else "nombre completo"
        captured_fields["mission_step"] = "nombre_razon_social"
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "solicitar_nombre_razon_social",
            [label],
            captured_fields,
            f"Listo. Comparteme la {label} para continuar con el registro.",
            False,
            "none",
        )

    document_type = str(captured_fields.get("new_client_document_type") or "").strip().lower()
    if profile_type == "clinica":
        if not document_type:
            normalized = normalize_lookup_key(text)
            if "camara" in normalized or "comercio" in normalized:
                document_type = "camara_comercio"
            elif "rut" in normalized:
                document_type = "rut"
            if document_type:
                captured_fields["new_client_document_type"] = document_type
    else:
        document_type = "tarjeta_profesional"
        captured_fields["new_client_document_type"] = document_type

    document_number = str(captured_fields.get("new_client_document_number") or "").strip()
    if not document_number:
        tagged = re.search(r"(?:numero|n[úu]mero|no|nro|#)?\s*[:\-]?\s*([A-Za-z0-9\-\.]{5,30})", text)
        if tagged:
            candidate = tagged.group(1).strip()
            if len(candidate) >= 5:
                document_number = candidate
                captured_fields["new_client_document_number"] = document_number

    if not document_type or not document_number:
        if profile_type == "clinica":
            captured_fields["mission_step"] = "documento_verificacion"
            return (
                "fase_2_recogida_datos",
                "fase_3_validacion",
                "in_progress",
                "solicitar_documento_verificacion",
                ["tipo y numero de documento (RUT o Camara de Comercio)"],
                captured_fields,
                "Gracias. Para validar la clinica, comparteme el documento y su numero (RUT o Camara de Comercio).",
                False,
                "none",
            )
        captured_fields["mission_step"] = "documento_verificacion"
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "solicitar_documento_verificacion",
            ["numero de tarjeta profesional"],
            captured_fields,
            "Gracias. Para validar el perfil profesional, comparteme el numero de tarjeta profesional.",
            False,
            "none",
        )

    contact_phone = str(captured_fields.get("new_client_contact_phone") or "").strip()
    if not contact_phone:
        extracted_phone = extract_phone(text)
        if extracted_phone:
            contact_phone = extracted_phone
            captured_fields["new_client_contact_phone"] = contact_phone

    if not contact_phone:
        captured_fields["mission_step"] = "telefono_contacto"
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "solicitar_telefono_contacto",
            ["telefono de contacto"],
            captured_fields,
            "Perfecto. Comparteme un telefono de contacto para seguimiento de aprobacion.",
            False,
            "none",
        )

    if has_attachment:
        captured_fields["new_client_document_attachment"] = "recibido"

    if str(captured_fields.get("new_client_document_attachment") or "") != "recibido":
        captured_fields["mission_step"] = "soporte_documental"
        return (
            "fase_3_validacion",
            "fase_7_escalado",
            "in_progress",
            "solicitar_soporte_documental",
            ["soporte documental"],
            captured_fields,
            "Para cerrar el registro, adjunta una foto o archivo del documento de verificacion.",
            False,
            "none",
        )

    captured_fields["new_client_review_status"] = "pending_manual_approval"
    captured_fields["mission_step"] = "pendiente_revision_humana"
    return (
        "fase_3_validacion",
        "fase_7_escalado",
        "pending_manual_approval",
        "pendiente_aprobacion_humana",
        [],
        captured_fields,
        "Listo, recibimos tus datos y soporte documental. Tu registro queda en revision humana y te confirmamos por este medio.",
        True,
        "operaciones",
    )


def handle_telegram_message(chat_id: int, text: str, has_attachment: bool = False) -> None:
    ensure_openai_warmup()
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
    onboarding_locked = is_new_client_onboarding_locked(
        session=session,
        session_service_area=session_service_area,
        service_area=session_service_area,
        requires_handoff=session_handoff_required,
    )

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

    used_openai_fallback = False
    openai_fallback_reason: str | None = None
    if openai_service is None:
        used_openai_fallback = True
        openai_fallback_reason = "service_unavailable"
        turn = build_openai_fallback_turn(ai_state)
    elif openai_circuit_active():
        print(f"[telegram] openai_circuit_active chat_id={chat_id}")
        used_openai_fallback = True
        openai_fallback_reason = "circuit_open"
        turn = build_openai_fallback_turn(ai_state)
    else:
        try:
            turn = openai_service.generate_turn(
                system_prompt=SYSTEM_PROMPT,
                user_message=text,
                state=ai_state,
            )
            register_openai_success()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            register_openai_failure()
            print(f"[telegram] openai_fallback reason={type(exc).__name__} chat_id={chat_id}")
            used_openai_fallback = True
            openai_fallback_reason = f"generation_error_{type(exc).__name__}"
            turn = build_openai_fallback_turn(ai_state)

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
    if not explicit_area and len(normalize_lookup_key(text)) >= 8 and not used_openai_fallback:
        semantic_area = detect_semantic_service_area_hint(text)
        if pending_route_identifier and semantic_area == "new_client" and not user_declares_not_registered(text):
            semantic_area = None
        if semantic_area:
            explicit_area = semantic_area
    numeric_menu_option = detect_numeric_menu_option(text)
    if numeric_menu_option in {"route_scheduling", "results", "accounting", "new_client"}:
        explicit_area = numeric_menu_option
    special_menu_option = detect_special_menu_option(text)
    access_segment_option = detect_access_segment_option(text)
    requested_flow_exit = user_requests_flow_exit(text)
    pending_segment_selection = bool(
        session and (session or {}).get("next_action") == "solicitar_segmento_cliente"
    )

    if pending_segment_selection and access_segment_option == "new_client":
        explicit_area = "new_client"
    elif pending_segment_selection and access_segment_option == "existing_client":
        explicit_area = None
        intent = "no_clasificado"
        service_area = "unknown"

    if onboarding_locked and explicit_area and explicit_area != "new_client" and not requested_flow_exit:
        numeric_choice = detect_numeric_menu_option(text)
        special_choice = detect_special_menu_option(text)
        if numeric_choice is None and special_choice is None and not is_explicit_intent_switch(text):
            explicit_area = "new_client"

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
    catalog_guidance_reply = build_catalog_guidance_reply(text)

    if pending_segment_selection and access_segment_option is None:
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "solicitar_segmento_cliente"
        message_mode = "flow_progress"
        resume_prompt = ""
        missing_fields = []
        reply = ACCESS_SEGMENT_CLARIFICATION_MESSAGE

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

    if pending_segment_selection and access_segment_option == "existing_client":
        captured_fields["access_segment"] = "existing_client"
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "solicitar_clasificacion"
        message_mode = "flow_progress"
        resume_prompt = ""
        missing_fields = []
        reply = INTENT_CLARIFICATION_MESSAGE

    if pending_segment_selection and access_segment_option == "new_client":
        captured_fields["access_segment"] = "new_client"

    if service_area == "unknown" and special_menu_option is None:
        recovery_area = detect_explicit_service_area(text)
        if not recovery_area and not used_openai_fallback:
            recovery_area = detect_semantic_service_area_hint(text)
        if onboarding_locked and recovery_area and recovery_area != "new_client" and not requested_flow_exit:
            recovery_area = None
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

    if onboarding_locked and requested_flow_exit:
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "solicitar_clasificacion"
        message_mode = "intent_switch"
        resume_prompt = ""
        missing_fields = []
        reply = (
            "Entendido, pausamos el registro de cliente nuevo. "
            "Indica ahora que gestion necesitas: recogida, resultados, pagos, PQRS u otra consulta."
        )
        if isinstance(captured_fields, dict):
            captured_fields.pop("active_mission", None)
            captured_fields.pop("mission_step", None)

    if not isinstance(captured_fields, dict):
        captured_fields = {}

    captured_fields = merge_captured_fields(ai_state.get("captured_fields"), captured_fields)
    pickup_time_window = str(captured_fields.get("pickup_time_window") or "").strip()
    legacy_time_window = str(captured_fields.get("time_window") or "").strip()
    if legacy_time_window and not pickup_time_window:
        captured_fields["pickup_time_window"] = legacy_time_window
        pickup_time_window = legacy_time_window
    if pickup_time_window and not legacy_time_window:
        captured_fields["time_window"] = pickup_time_window

    missing_fields = [str(item) for item in missing_fields if item is not None]
    missing_fields = prune_missing_fields_with_captured(missing_fields, captured_fields)
    reply = enforce_service_area_reply_quality(
        service_area=service_area,
        reply=reply,
        missing_fields=missing_fields,
    )
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

    if (
        not is_first_turn
        and service_area == "results"
        and session_service_area == "results"
        and (is_catalog_inquiry(text) or is_help_inquiry(text))
        and not extract_results_reference(text)
    ):
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        next_action = "atender_otra_consulta"
        missing_fields = []
        message_mode = "intent_switch"
        resume_prompt = ""
        reply = catalog_guidance_reply or (
            "Puedo orientarte con catalogo, precios referenciales y proceso operativo. "
            "Indica examen o necesidad puntual."
        )

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
                    "Dato recibido. Estoy validando el estado del resultado y te confirmo enseguida."
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
            next_action = "solicitar_segmento_cliente"
            phase_current = "fase_1_clasificacion"
        elif should_split_first_greeting(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
            next_action = "solicitar_segmento_cliente"
            phase_current = "fase_1_clasificacion"
        elif catalog_guidance_reply:
            reply = catalog_guidance_reply
            follow_up_message = ""
            next_action = "atender_otra_consulta"
            phase_current = "fase_1_clasificacion"
        else:
            reply = INITIAL_GREETING_MESSAGE
            phase_current = "fase_0_bienvenida"
            next_action = "solicitar_segmento_cliente"
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
        known_access_segment = str(captured_fields.get("access_segment") or "").strip().lower()
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
            next_action = "solicitar_segmento_cliente"
        elif is_greeting_only(text):
            reply = INITIAL_GREETING_MESSAGE
            follow_up_message = ""
            next_action = "solicitar_segmento_cliente"
        else:
            if known_access_segment == "existing_client":
                reply = INTENT_CLARIFICATION_MESSAGE
                next_action = "solicitar_clasificacion"
            else:
                reply = ACCESS_SEGMENT_CLARIFICATION_MESSAGE
                next_action = "solicitar_segmento_cliente"

    if (
        catalog_guidance_reply
        and special_menu_option is None
        and service_area == "unknown"
        and (is_catalog_inquiry(text) or is_help_inquiry(text))
        and not is_greeting_only(text)
    ):
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "atender_otra_consulta"
        missing_fields = []
        message_mode = "intent_switch"
        resume_prompt = ""
        reply = catalog_guidance_reply
        follow_up_message = ""

    if (
        is_non_eligible_final_consumer(text)
        and is_price_or_services_inquiry(text)
        and not client_id
    ):
        intent = "no_clasificado"
        service_area = "unknown"
        phase_current = "fase_1_clasificacion"
        phase_next = "fase_2_recogida_datos"
        status = "in_progress"
        requires_handoff = False
        handoff_area = "none"
        next_action = "solicitar_segmento_cliente"
        missing_fields = []
        message_mode = "flow_progress"
        resume_prompt = ""
        reply = (
            "Por politica de A3, los valores y gestion operativa se entregan solo a clinicas y medicos veterinarios. "
            "Si eres profesional, indica por favor: 1) cliente nuevo o 2) ya cliente de A3."
        )

    if service_area == "new_client" and not requires_handoff:
        (
            phase_current,
            phase_next,
            status,
            next_action,
            missing_fields,
            captured_fields,
            guarded_reply,
            requires_handoff,
            handoff_area,
        ) = apply_new_client_onboarding_guard(
            text=text,
            captured_fields=captured_fields,
            has_attachment=has_attachment,
        )
        reply = guarded_reply
        message_mode = "flow_progress"
        resume_prompt = ""

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
            next_action = "solicitar_tipo_cliente"
            message_mode = "flow_progress"
            resume_prompt = ""
            missing_fields = []
            reply = NEW_CLIENT_REGISTRATION_MESSAGE
        else:
            attempts = int(captured_fields.get("route_identification_attempts", 0) or 0) + 1
            captured_fields["route_identification_attempts"] = attempts

            if (
                is_catalog_inquiry(text)
                and not is_route_operational_request(text)
                and detect_explicit_service_area(text) != "route_scheduling"
            ) or is_help_inquiry(text):
                service_area = "unknown"
                intent = "no_clasificado"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "atender_otra_consulta"
                message_mode = "intent_switch"
                resume_prompt = ""
                missing_fields = []
                reply = catalog_guidance_reply or (
                    "Puedo orientarte con catalogo, precios referenciales y proceso operativo. "
                    "Indica examen o necesidad puntual."
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
                    "Si prefieres otra gestion, escribe 2, 3, 4 o 5 del menu."
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
            elif is_catalog_inquiry(text) or is_help_inquiry(text):
                intent = "no_clasificado"
                service_area = "unknown"
                phase_current = "fase_1_clasificacion"
                phase_next = "fase_2_recogida_datos"
                status = "in_progress"
                next_action = "atender_otra_consulta"
                missing_fields = []
                message_mode = "intent_switch"
                resume_prompt = ""
                reply = catalog_guidance_reply or (
                    "Puedo orientarte con catalogo, precios referenciales y proceso operativo. "
                    "Indica examen o necesidad puntual."
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
                    reply = "Contabilidad activa. Comparte detalle del caso, NIF y si tienes numero de factura."
                elif service_area == "new_client":
                    next_action = "solicitar_tipo_cliente"
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
                time_window_label = str(captured_fields.get("pickup_time_window") or "").strip()
                time_window_suffix = f" en franja {time_window_label}" if time_window_label else ""
                reply = (
                    "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                    f"¿El retiro es en la direccion habitual de {clinic_label} ({address_label}){time_window_suffix}? "
                    "Responde: habitual o nueva direccion."
                )
            elif next_action == "solicitar_direccion_actualizada":
                reply = "Perfecto, por favor comparteme la direccion actual para programar el retiro."
            elif next_action == "confirmar_programacion_ruta":
                time_window_label = str(captured_fields.get("pickup_time_window") or "").strip()
                time_window_note = f" Franja registrada: {time_window_label}." if time_window_label else ""
                if (session or {}).get("next_action") == "solicitar_direccion_actualizada":
                    reply = (
                        "Listo, registre la nueva direccion de retiro y tu solicitud quedo programada. "
                        f"Te confirmaremos cualquier novedad por este medio.{time_window_note}"
                    )
                else:
                    reply = (
                        "Listo, tu solicitud de retiro de muestra quedo programada. "
                        f"Te confirmaremos cualquier novedad por este medio.{time_window_note}"
                    )
            elif next_action == "continuar_conversacion":
                reply = (
                    "Solicitud programada. "
                    "Si necesitas otra gestion, elige: 2 resultados, 3 pagos, 4 PQRS o 5 otras consultas."
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
                    time_window_label = str(captured_fields.get("pickup_time_window") or "").strip()
                    time_window_suffix = f" en franja {time_window_label}" if time_window_label else ""
                    reply = (
                        "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                        f"¿El retiro es en la direccion habitual de {clinic_label} ({address_label}){time_window_suffix}? "
                        "Responde: habitual o nueva direccion."
                    )

            resume_prompt = ""
            message_mode = "flow_progress"

    if should_share_new_client_registration(
        service_area=service_area,
        requires_handoff=requires_handoff,
        reply=reply,
        next_action=next_action,
    ):
        reply = NEW_CLIENT_REGISTRATION_MESSAGE
        next_action = "solicitar_tipo_cliente"
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
        elif service_area == "new_client":
            if next_action == "solicitar_tipo_cliente":
                reply = (
                    "Para continuar el alta, confirmame si trabajas como clinica veterinaria o como medico veterinario independiente."
                )
            elif next_action == "solicitar_nombre_razon_social":
                reply = "Comparte la razon social (clinica) o nombre completo (independiente)."
            elif next_action == "solicitar_documento_verificacion":
                reply = "Indica tipo y numero de documento de verificacion para continuar."
            elif next_action == "solicitar_telefono_contacto":
                reply = "Comparte un telefono de contacto para seguimiento de aprobacion."
            elif next_action == "solicitar_soporte_documental":
                reply = "Adjunta foto o archivo del documento para revision humana."
            else:
                reply = (
                    "Tu registro sigue en curso. Continuemos con el siguiente dato para revision humana."
                )
            anti_loop_prompt = ""
        else:
            anti_loop_prompt = build_resume_question(missing_fields)
        if anti_loop_prompt and anti_loop_prompt.lower() not in reply.lower():
            reply = f"{reply} {anti_loop_prompt}".strip()

    if phase_next not in FLOW_STAGE_ORDER:
        phase_next = next_phase_from_current(phase_current)

    if isinstance(captured_fields, dict):
        pickup_time_window = str(captured_fields.get("pickup_time_window") or "").strip()
        legacy_time_window = str(captured_fields.get("time_window") or "").strip()
        if pickup_time_window and not legacy_time_window:
            captured_fields["time_window"] = pickup_time_window
        elif legacy_time_window and not pickup_time_window:
            captured_fields["pickup_time_window"] = legacy_time_window

    if phone and isinstance(captured_fields, dict) and "phone" not in captured_fields:
        captured_fields["phone"] = phone

    request_priority = "normal"
    if service_area == "route_scheduling":
        request_priority = detect_route_priority(text, captured_fields)
        captured_fields["priority"] = request_priority
        if request_priority == "urgent" and "prioridad urgente" not in reply.lower():
            reply = f"{reply} Lo marco con prioridad urgente para agilizar la recoleccion.".strip()

    scheduled_pickup_date = (
        calculate_schedule(datetime.now().isoformat(), settings.cutoff_time)[
            "scheduled_pickup_date"
        ]
        if service_area == "route_scheduling"
        else None
    )

    is_route_programmed_reply = "quedo programada" in reply.lower()
    if service_area == "route_scheduling" and (
        next_action == "confirmar_programacion_ruta" or is_route_programmed_reply
    ):
        pickup_date_label = format_route_pickup_date_label(scheduled_pickup_date)
        if pickup_date_label and "retiro estimado" not in reply.lower():
            reply = (
                f"{reply} Super, ya quedo diligenciado y el retiro estimado es para {pickup_date_label}."
            ).strip()

    request_ref = create_base_request(
        client_id=client_id,
        service_area=service_area,
        intent=intent,
        priority=request_priority,
        pickup_address=None,
        scheduled_pickup_date=scheduled_pickup_date,
    )

    if (
        service_area == "new_client"
        and next_action == "pendiente_aprobacion_humana"
        and isinstance(captured_fields, dict)
        and captured_fields.get("approval_event_sent") != "true"
    ):
        try:
            supabase.create_request_event(
                request_id=request_ref["id"],
                event_type="new_client_pending_review",
                event_payload={
                    "profile_type": captured_fields.get("new_client_profile_type"),
                    "legal_name": captured_fields.get("new_client_legal_name"),
                    "document_type": captured_fields.get("new_client_document_type"),
                    "document_number": captured_fields.get("new_client_document_number"),
                    "contact_phone": captured_fields.get("new_client_contact_phone"),
                },
            )
            captured_fields["approval_event_sent"] = "true"
        except httpx.HTTPStatusError:
            print(f"[telegram] new_client_pending_review_event_failed chat_id={chat_id}")

    if used_openai_fallback and openai_fallback_reason:
        try:
            supabase.create_request_event(
                request_id=request_ref["id"],
                event_type="openai_generation_error",
                event_payload={
                    "reason": openai_fallback_reason,
                    "fallback_used": True,
                    "circuit_active": openai_circuit_active(),
                    "model": getattr(openai_service, "model", None),
                    "fallback_model": getattr(openai_service, "fallback_model", None),
                },
            )
        except httpx.HTTPStatusError:
            print(f"[telegram] openai_fallback_event_unavailable chat_id={chat_id}")

    automation_note = ""
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
        chat_id, text, has_attachment = get_message_from_update(update)
    except ValueError:
        return
    handle_telegram_message(chat_id, text, has_attachment)


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


def extract_whatsapp_incoming_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    entries = payload.get("entry") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return rows

    for entry in entries:
        changes = entry.get("changes") if isinstance(entry, dict) else []
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else {}
            messages = value.get("messages") if isinstance(value, dict) else []
            if not isinstance(messages, list):
                continue

            for message in messages:
                if not isinstance(message, dict):
                    continue
                wa_from = str(message.get("from") or "").strip()
                msg_type = str(message.get("type") or "").strip().lower()
                text_body = ""

                if msg_type == "text":
                    text_obj = message.get("text") if isinstance(message.get("text"), dict) else {}
                    text_body = str(text_obj.get("body") or "").strip()
                elif msg_type in {"image", "document", "audio", "video", "sticker"}:
                    text_body = f"[{msg_type}]"

                if wa_from and text_body:
                    rows.append({"from": wa_from, "text": text_body, "type": msg_type or "text"})

    return rows


def process_whatsapp_inbound_message(*, wa_from: str, text: str, msg_type: str) -> None:
    client = None
    try:
        client = supabase.get_client_by_phone(wa_from)
    except httpx.HTTPStatusError:
        client = None

    client_id = client.get("id") if isinstance(client, dict) else None
    try:
        request_ref = create_base_request(
            client_id=client_id,
            service_area="unknown",
            intent="unknown",
            priority="normal",
            pickup_address=None,
            scheduled_pickup_date=None,
        )
    except httpx.HTTPStatusError:
        request_ref = {"id": None}

    try:
        if request_ref.get("id"):
            supabase.create_request_event(
                request_id=request_ref["id"],
                event_type="whatsapp_inbound_received",
                event_payload={
                    "from": wa_from,
                    "message_type": msg_type,
                    "message_text": text,
                },
            )
        supabase.create_telegram_message_event(
            {
                "channel": "whatsapp",
                "external_chat_id": wa_from,
                "client_id": client_id,
                "request_id": request_ref.get("id"),
                "direction": "user",
                "message_text": text,
                "phase_snapshot": "fase_1_clasificacion",
                "intent_snapshot": "no_clasificado",
                "service_area_snapshot": "unknown",
                "captured_fields_snapshot": {},
                "metadata": {"source": "whatsapp_webhook"},
                "created_at": datetime.now().isoformat(),
            }
        )
    except httpx.HTTPStatusError:
        pass

    if whatsapp_service:
        ack = (
            "Gracias por escribir a A3. Recibimos tu mensaje y te atenderemos por este canal. "
            "Mientras terminamos la migracion operativa, algunas solicitudes pueden pasar a validacion humana."
        )
        try:
            whatsapp_service.send_text(wa_from, ack)
        except httpx.HTTPError:
            pass


def apply_new_client_review_decision(
    *,
    external_chat_id: str,
    decision: str,
    reviewer: str,
    reason: str,
) -> tuple[bool, str]:
    normalized_chat_id = str(external_chat_id or "").strip()
    if not normalized_chat_id:
        return False, "Falta el chat ID del registro."

    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        return False, "Decision invalida."

    if settings.dashboard_data_mode == "mock":
        return True, "Accion simulada en modo mock."

    session_rows = safe_fetch(
        lambda: supabase.fetch_rows(
            "telegram_sessions",
            {
                "external_chat_id": f"eq.{normalized_chat_id}",
                "select": "external_chat_id,request_id,captured_fields",
                "limit": "1",
            },
        ),
        [],
    )
    if not session_rows:
        return False, "No se encontro el registro solicitado."

    session_row = session_rows[0]
    captured_fields = (
        dict(session_row.get("captured_fields"))
        if isinstance(session_row.get("captured_fields"), dict)
        else {}
    )

    now_iso = datetime.now().isoformat()
    new_status = "approved_manual" if normalized_decision == "approve" else "rejected_manual"
    captured_fields["new_client_review_status"] = new_status
    captured_fields["new_client_review_by"] = reviewer or "operador"
    captured_fields["new_client_review_at"] = now_iso
    captured_fields["new_client_review_reason"] = (reason or "").strip() or "sin comentario"
    if normalized_decision == "approve":
        captured_fields["access_segment"] = "existing_client"
        captured_fields["customer_lifecycle_stage"] = "frecuente_habilitado"
    else:
        captured_fields["customer_lifecycle_stage"] = "registro_rechazado"

    try:
        supabase.update_rows(
            "telegram_sessions",
            {"external_chat_id": f"eq.{normalized_chat_id}"},
            {
                "captured_fields": captured_fields,
                "status": "in_progress" if normalized_decision == "approve" else "closed",
                "phase_current": "fase_6_cierre" if normalized_decision == "approve" else "fase_7_escalado",
                "phase_next": "fase_1_clasificacion" if normalized_decision == "approve" else "fase_7_escalado",
                "next_action": "solicitar_clasificacion" if normalized_decision == "approve" else "continuar_conversacion",
                "updated_at": now_iso,
            },
        )
    except httpx.HTTPStatusError:
        return False, "No fue posible actualizar el estado de aprobacion."

    request_id = str(session_row.get("request_id") or "").strip()
    if request_id:
        try:
            supabase.create_request_event(
                request_id=request_id,
                event_type="new_client_review_decision",
                event_payload={
                    "decision": new_status,
                    "reviewer": reviewer or "operador",
                    "reviewed_at": now_iso,
                    "external_chat_id": normalized_chat_id,
                    "promoted_to_frequent": normalized_decision == "approve",
                    "reason": captured_fields.get("new_client_review_reason"),
                },
            )
        except httpx.HTTPStatusError:
            pass

    try:
        chat_id = int(normalized_chat_id)
    except ValueError:
        chat_id = None

    if chat_id is not None:
        if normalized_decision == "approve":
            notify_message = (
                "Tu registro como cliente profesional fue aprobado. "
                "Desde ahora puedes continuar como cliente frecuente en el flujo operativo de A3."
            )
        else:
            reason_suffix = (
                f" Motivo: {captured_fields.get('new_client_review_reason')}."
                if captured_fields.get("new_client_review_reason")
                else ""
            )
            notify_message = (
                "Tu registro no pudo ser aprobado por ahora. "
                "Si deseas, responde a este chat para ajustar la documentacion y reenviar la solicitud."
                f"{reason_suffix}"
            )
        try:
            telegram.send_message(chat_id, notify_message)
        except httpx.HTTPError:
            pass

    if normalized_decision == "approve":
        return True, "Cliente aprobado correctamente."
    return True, "Cliente rechazado correctamente."


def add_clinic_professional_affiliation(
    *,
    clinic_key: str,
    clinic_name: str,
    professional_name: str,
    professional_card: str,
) -> tuple[bool, str]:
    normalized_clinic_key = normalize_lookup_key(clinic_key or clinic_name)
    normalized_prof_name = (professional_name or "").strip()
    normalized_prof_card = (professional_card or "").strip()
    if not normalized_clinic_key:
        return False, "Debes indicar la clinica."
    if not normalized_prof_name:
        return False, "Debes indicar el nombre del medico veterinario."

    if settings.dashboard_data_mode == "mock":
        return True, "Afiliacion simulada en modo mock."

    professional_key = normalize_lookup_key(f"{normalized_prof_name}|{normalized_prof_card}")
    if not professional_key:
        return False, "No se pudo construir la clave del profesional."

    payload = {
        "clinic_key": normalized_clinic_key,
        "professional_key": professional_key,
        "professional_name": normalized_prof_name,
        "professional_card": normalized_prof_card or None,
        "source_sheet": "dashboard_manual",
    }

    try:
        supabase.insert_rows(
            "clients_a3_professionals",
            [payload],
            upsert=True,
            on_conflict="clinic_key,professional_key,source_sheet",
        )
    except httpx.HTTPStatusError:
        return False, "No fue posible guardar la afiliacion."

    clean_clinic_name = (clinic_name or "").strip()
    if clean_clinic_name:
        try:
            supabase.insert_rows(
                "clients_a3_knowledge",
                [
                    {
                        "clinic_key": normalized_clinic_key,
                        "clinic_name": clean_clinic_name,
                        "is_registered": True,
                        "is_new_client": False,
                        "source_excel": "dashboard_manual",
                        "source_updated_at": datetime.now().isoformat(),
                    }
                ],
                upsert=True,
                on_conflict="clinic_key",
            )
        except httpx.HTTPStatusError:
            pass

    return True, "Afiliacion guardada correctamente."


def remove_clinic_professional_affiliation(
    *,
    clinic_key: str,
    professional_key: str,
) -> tuple[bool, str]:
    normalized_clinic_key = normalize_lookup_key(clinic_key)
    normalized_professional_key = normalize_lookup_key(professional_key)
    if not normalized_clinic_key or not normalized_professional_key:
        return False, "Datos incompletos para desvincular."

    if settings.dashboard_data_mode == "mock":
        return True, "Desvinculacion simulada en modo mock."

    try:
        removed = supabase.delete_rows(
            "clients_a3_professionals",
            {
                "clinic_key": f"eq.{normalized_clinic_key}",
                "professional_key": f"eq.{normalized_professional_key}",
            },
        )
    except httpx.HTTPStatusError:
        return False, "No fue posible desvincular el profesional."

    if removed <= 0:
        return False, "No se encontro afiliacion para desvincular."
    return True, "Profesional desvinculado correctamente."


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


@app.get("/aprobaciones")
@login_required
def approvals_page() -> Any:
    context = build_dashboard_context()
    query = (request.args.get("q") or "").strip()
    profile = (request.args.get("profile") or "all").strip().lower()
    since = (request.args.get("since") or "").strip()

    approval_rows = context.get("approval_rows") if isinstance(context.get("approval_rows"), list) else []
    context["approval_rows"] = filter_pending_approval_rows(
        approval_rows,
        query=query,
        profile_type=profile,
        since_date=since,
    )

    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="aprobaciones",
        notice=(request.args.get("notice") or "").strip(),
        notice_type=(request.args.get("notice_type") or "info").strip(),
        approval_filter_q=query,
        approval_filter_profile=profile,
        approval_filter_since=since,
    )


@app.post("/aprobaciones/decision")
@login_required
def approval_decision() -> Any:
    external_chat_id = (request.form.get("external_chat_id") or "").strip()
    decision = (request.form.get("decision") or "").strip().lower()
    reviewer = str(session.get("username") or "operador")
    reason = (request.form.get("reason") or "").strip()
    current_q = (request.form.get("q") or "").strip()
    current_profile = (request.form.get("profile") or "all").strip().lower()
    current_since = (request.form.get("since") or "").strip()

    if decision == "reject" and not reason:
        return redirect(
            url_for(
                "approvals_page",
                notice="Debes indicar un motivo para rechazar.",
                notice_type="error",
                q=current_q,
                profile=current_profile,
                since=current_since,
            )
        )

    ok, message = apply_new_client_review_decision(
        external_chat_id=external_chat_id,
        decision=decision,
        reviewer=reviewer,
        reason=reason,
    )

    return redirect(
        url_for(
            "approvals_page",
            notice=message,
            notice_type="ok" if ok else "error",
            q=current_q,
            profile=current_profile,
            since=current_since,
        )
    )


@app.get("/afiliaciones")
@login_required
def affiliations_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="afiliaciones",
        notice=(request.args.get("notice") or "").strip(),
        notice_type=(request.args.get("notice_type") or "info").strip(),
    )


@app.post("/afiliaciones/agregar")
@login_required
def affiliation_add() -> Any:
    clinic_key = (request.form.get("clinic_key") or "").strip()
    clinic_name = (request.form.get("clinic_name") or "").strip()
    professional_name = (request.form.get("professional_name") or "").strip()
    professional_card = (request.form.get("professional_card") or "").strip()

    ok, message = add_clinic_professional_affiliation(
        clinic_key=clinic_key,
        clinic_name=clinic_name,
        professional_name=professional_name,
        professional_card=professional_card,
    )

    return redirect(
        url_for(
            "affiliations_page",
            notice=message,
            notice_type="ok" if ok else "error",
        )
    )


@app.post("/afiliaciones/desvincular")
@login_required
def affiliation_remove() -> Any:
    clinic_key = (request.form.get("clinic_key") or "").strip()
    professional_key = (request.form.get("professional_key") or "").strip()

    ok, message = remove_clinic_professional_affiliation(
        clinic_key=clinic_key,
        professional_key=professional_key,
    )

    return redirect(
        url_for(
            "affiliations_page",
            notice=message,
            notice_type="ok" if ok else "error",
        )
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


@app.get("/webhooks/whatsapp")
def whatsapp_webhook_verify() -> Any:
    mode = (request.args.get("hub.mode") or "").strip()
    token = (request.args.get("hub.verify_token") or "").strip()
    challenge = (request.args.get("hub.challenge") or "").strip()

    if mode == "subscribe" and token and token == settings.whatsapp_webhook_verify_token:
        return challenge, 200
    return jsonify({"error": "Invalid WhatsApp verification"}), 403


@app.post("/webhooks/whatsapp")
def whatsapp_webhook() -> Any:
    payload = request.get_json(silent=True) or {}
    incoming_messages = extract_whatsapp_incoming_messages(payload)
    if not incoming_messages:
        return jsonify({"ok": True, "processed": 0})

    processed = 0
    for item in incoming_messages:
        process_whatsapp_inbound_message(
            wa_from=item["from"],
            text=item["text"],
            msg_type=item.get("type") or "text",
        )
        processed += 1

    return jsonify({"ok": True, "processed": processed})


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
