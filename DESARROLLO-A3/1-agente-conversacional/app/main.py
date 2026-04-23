from __future__ import annotations

import re
import json
import hashlib
import time
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
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

CLIENT_TYPE_OPTIONS = {
    "es_persona": "Es Persona",
    "empresa": "Empresa",
    "otro": "Otro",
}

VAT_REGIME_OPTIONS = {
    "no_responsable_iva": "No responsable de IVA",
    "responsable_iva": "Responsable de IVA",
}

REQUEST_PRIORITY_OPTIONS: list[tuple[str, str]] = [
    ("normal", "Normal"),
    ("high", "Alta"),
    ("urgent", "Urgente"),
]
REQUEST_PRIORITY_LABELS = {key: label for key, label in REQUEST_PRIORITY_OPTIONS}
REQUEST_PRIORITY_DB_MAP = {
    "normal": "normal",
    "high": "urgent",
    "urgent": "urgent",
}

REQUEST_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("received", "Recibida"),
    ("assigned", "Asignada"),
    ("on_route", "En camino"),
    ("picked_up", "Retirada"),
    ("in_lab", "En laboratorio"),
    ("processed", "Procesada"),
    ("sent", "Resultados enviados"),
    ("cancelled", "Cancelada"),
    ("error_pending_assignment", "Pendiente de asignacion"),
]
REQUEST_STATUS_LABELS = {key: label for key, label in REQUEST_STATUS_OPTIONS}

SAMPLE_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("pending_pickup", "A retirar"),
    ("picked_up", "Retirada"),
    ("on_route", "En camino"),
    ("received_lab", "Recibida en laboratorio"),
    ("in_lab", "En laboratorio"),
    ("in_analysis", "En analisis"),
    ("processed", "Procesada"),
    ("ready_results", "Resultados listos"),
    ("delivered_results", "Resultados entregados"),
    ("cancelled", "Cancelada"),
]
SAMPLE_STATUS_LABELS = {key: label for key, label in SAMPLE_STATUS_OPTIONS}
SAMPLE_STATUS_DB_OPTIONS = {
    "pending_pickup",
    "on_route",
    "received_lab",
    "in_analysis",
    "ready_results",
    "delivered_results",
    "cancelled",
}
SAMPLE_STATUS_DB_FALLBACK = {
    "picked_up": "on_route",
    "in_lab": "in_analysis",
    "processed": "in_analysis",
}

BOGOTA_LOCALITIES: list[dict[str, Any]] = [
    {
        "code": "usaquen",
        "name": "Usaquen",
        "aliases": ["usaquen", "usaquen norte"],
        "lat": 4.7059,
        "lng": -74.0308,
    },
    {
        "code": "chapinero",
        "name": "Chapinero",
        "aliases": ["chapinero", "chapinero alto"],
        "lat": 4.6486,
        "lng": -74.0628,
    },
    {
        "code": "santa_fe",
        "name": "Santa Fe",
        "aliases": ["santa fe", "santafe"],
        "lat": 4.6036,
        "lng": -74.0724,
    },
    {
        "code": "san_cristobal",
        "name": "San Cristobal",
        "aliases": ["san cristobal", "san cristobal sur"],
        "lat": 4.5685,
        "lng": -74.0831,
    },
    {
        "code": "usme",
        "name": "Usme",
        "aliases": ["usme"],
        "lat": 4.4774,
        "lng": -74.1178,
    },
    {
        "code": "tunjuelito",
        "name": "Tunjuelito",
        "aliases": ["tunjuelito"],
        "lat": 4.5804,
        "lng": -74.1305,
    },
    {
        "code": "bosa",
        "name": "Bosa",
        "aliases": ["bosa"],
        "lat": 4.6158,
        "lng": -74.1946,
    },
    {
        "code": "kennedy",
        "name": "Kennedy",
        "aliases": ["kennedy", "ciudad kennedy"],
        "lat": 4.6267,
        "lng": -74.1512,
    },
    {
        "code": "fontibon",
        "name": "Fontibon",
        "aliases": ["fontibon", "fontibon aeropuerto"],
        "lat": 4.6784,
        "lng": -74.1425,
    },
    {
        "code": "engativa",
        "name": "Engativa",
        "aliases": ["engativa", "engativa pueblo"],
        "lat": 4.6953,
        "lng": -74.1129,
    },
    {
        "code": "suba",
        "name": "Suba",
        "aliases": ["suba"],
        "lat": 4.7473,
        "lng": -74.0842,
    },
    {
        "code": "barrios_unidos",
        "name": "Barrios Unidos",
        "aliases": ["barrios unidos"],
        "lat": 4.6694,
        "lng": -74.0742,
    },
    {
        "code": "teusaquillo",
        "name": "Teusaquillo",
        "aliases": ["teusaquillo"],
        "lat": 4.6387,
        "lng": -74.0918,
    },
    {
        "code": "los_martires",
        "name": "Los Martires",
        "aliases": ["los martires", "martires"],
        "lat": 4.6038,
        "lng": -74.0911,
    },
    {
        "code": "antonio_narino",
        "name": "Antonio Narino",
        "aliases": ["antonio narino"],
        "lat": 4.5894,
        "lng": -74.1019,
    },
    {
        "code": "puente_aranda",
        "name": "Puente Aranda",
        "aliases": ["puente aranda"],
        "lat": 4.6169,
        "lng": -74.1083,
    },
    {
        "code": "la_candelaria",
        "name": "La Candelaria",
        "aliases": ["la candelaria", "candelaria"],
        "lat": 4.5962,
        "lng": -74.0733,
    },
    {
        "code": "rafael_uribe_uribe",
        "name": "Rafael Uribe Uribe",
        "aliases": ["rafael uribe uribe", "rafael uribe"],
        "lat": 4.5653,
        "lng": -74.1065,
    },
    {
        "code": "ciudad_bolivar",
        "name": "Ciudad Bolivar",
        "aliases": ["ciudad bolivar", "cd bolivar"],
        "lat": 4.5307,
        "lng": -74.1525,
    },
    {
        "code": "sumapaz",
        "name": "Sumapaz",
        "aliases": ["sumapaz"],
        "lat": 4.2503,
        "lng": -74.2834,
    },
]

BOGOTA_LOCALITIES_BY_CODE = {row["code"]: row for row in BOGOTA_LOCALITIES}
BOGOTA_LOCALITY_CODES = set(BOGOTA_LOCALITIES_BY_CODE.keys())

COURIER_COLOR_PALETTE = [
    "#f97316",
    "#0ea5e9",
    "#22c55e",
    "#eab308",
    "#ec4899",
    "#a855f7",
    "#14b8a6",
    "#f43f5e",
    "#6366f1",
    "#84cc16",
]

LOCALITIES_GEOJSON_URL = (
    "https://raw.githubusercontent.com/NataliaGarzon/Localidades/master/"
    "poligonos-localidades.geojson"
)


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
NEW_CLIENT_MANUAL_HANDOFF_MESSAGE = (
    "Gracias por escribirnos. Como eres cliente nuevo, te vamos a redirigir a atencion al cliente "
    "para que el equipo de recepcion y servicio al cliente complete tu registro manualmente "
    "y continue con tu solicitud."
)
ROUTE_CLIENT_IDENTIFICATION_MESSAGE = (
    "Perfecto, te ayudo con eso. "
    "Primero necesito confirmar si ya estas registrado. "
    "Comparteme tu NIF o dime el nombre de la veterinaria para ubicar tu registro. "
    "Si aun no estas registrado, te ayudo a hacerlo ahora."
)
ROUTE_ALREADY_PROGRAMMED_MESSAGE = (
    "Tu solicitud ya quedó programada. "
    "Si deseas, puedo ayudarte ahora con resultados, pagos, PQRS u otra consulta."
)
ROUTE_CHAT_CLOSURE_MESSAGE = (
    "Perfecto, quedamos atentos. "
    "Cuando necesites apoyo con resultados, pagos, PQRS u otra consulta, me escribes."
)
ROUTE_CANCELLATION_MESSAGE = (
    "Entendido, cancele la solicitud de programacion de ruta en este chat. "
    "Si deseas retomarla mas tarde o necesitas otra gestion, te apoyo de inmediato."
)
ROUTE_CLIENT_NAME_VALIDATION_MESSAGE = (
    "No pude ubicar ese NIT/NID en este momento. "
    "Para continuar, comparteme por favor el nombre de la veterinaria tal como aparece en el registro."
)
ROUTE_CLIENT_TAX_VALIDATION_MESSAGE = (
    "No pude ubicar ese nombre de veterinaria. "
    "Para continuar, comparteme por favor el NIT/NID (con o sin digito de verificacion)."
)
ROUTE_CLIENT_VALIDATION_HANDOFF_MESSAGE = (
    "Te vamos a pasar a atencion al cliente para validar tu informacion y continuar con tu solicitud."
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


def is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = normalize_lookup_key(str(value or ""))
    return normalized in {"1", "true", "yes", "si", "on"}


def normalize_locality_code(value: Any) -> str:
    normalized = normalize_lookup_key(str(value or ""))
    if not normalized:
        return ""
    return normalized.replace(" ", "_")


def courier_color_for_id(courier_id: str) -> str:
    normalized = (courier_id or "").strip()
    if not normalized:
        return "#475569"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    palette_index = int(digest[:2], 16) % len(COURIER_COLOR_PALETTE)
    return COURIER_COLOR_PALETTE[palette_index]


def resolve_bogota_locality(value: Any) -> dict[str, Any] | None:
    normalized_text = normalize_lookup_key(str(value or ""))
    if not normalized_text:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in BOGOTA_LOCALITIES:
        aliases = [row["name"], row["code"], *row.get("aliases", [])]
        for alias in aliases:
            alias_key = normalize_lookup_key(str(alias or ""))
            if not alias_key:
                continue
            if normalized_text == alias_key:
                candidates.append((len(alias_key) + 200, row))
                continue
            if f" {alias_key} " in f" {normalized_text} ":
                candidates.append((len(alias_key), row))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def normalize_phone_lookup(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) > 10:
        return digits[-10:]
    return digits


def normalize_courier_phone_value(value: Any) -> str:
    raw_text = str(value or "").strip()
    if not raw_text:
        return ""

    compact = re.sub(r"\s+", "", raw_text)
    has_plus_prefix = compact.startswith("+")
    digits = re.sub(r"\D+", "", compact)
    if len(digits) < 7:
        return ""

    if has_plus_prefix:
        return f"+{digits}"
    return digits


def normalize_bool_option_value(value: Any) -> bool | None:
    normalized = normalize_lookup_key(str(value or ""))
    if not normalized:
        return None
    if normalized in {"si", "s", "yes", "true", "1", "ok", "x", "registrado", "ingresado"}:
        return True
    if normalized in {"no", "n", "false", "0", "pendiente"}:
        return False
    return None


def bool_to_option(value: Any) -> str:
    if value is True:
        return "si"
    if value is False:
        return "no"
    return ""


def format_bool_option(value: Any) -> str:
    option = bool_to_option(value)
    if option == "si":
        return "Si"
    if option == "no":
        return "No"
    return "Sin dato"


def normalize_client_type_value(value: Any) -> str:
    normalized = normalize_lookup_key(str(value or ""))
    if not normalized:
        return ""
    if normalized in CLIENT_TYPE_OPTIONS:
        return normalized
    if "persona" in normalized:
        return "es_persona"
    if "empresa" in normalized:
        return "empresa"
    if "otro" in normalized:
        return "otro"
    return ""


def normalize_vat_regime_value(value: Any) -> str:
    normalized = normalize_lookup_key(str(value or ""))
    if not normalized:
        return ""
    if normalized in VAT_REGIME_OPTIONS:
        return normalized
    if "no" in normalized and "responsable" in normalized:
        return "no_responsable_iva"
    if "responsable" in normalized:
        return "responsable_iva"
    return ""


def sanitize_profile_text(value: Any, max_length: int = 400) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > max_length:
        text = text[:max_length]
    return text


def parse_knowledge_sources_payload(raw_value: Any) -> tuple[list[str], dict[str, Any]]:
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value if str(item).strip()], {}

    if isinstance(raw_value, dict):
        sources_raw = raw_value.get("sources")
        sources: list[str] = []
        if isinstance(sources_raw, list):
            sources = [str(item) for item in sources_raw if str(item).strip()]

        profile_raw = raw_value.get("legacy_profile")
        if isinstance(profile_raw, dict):
            return sources, dict(profile_raw)

        return sources, {}

    return [], {}


def build_knowledge_sources_payload(raw_value: Any, profile_updates: dict[str, Any]) -> dict[str, Any]:
    sources, profile = parse_knowledge_sources_payload(raw_value)
    if not sources:
        sources = ["dashboard_manual"]

    merged_profile = dict(profile)
    for key, value in profile_updates.items():
        merged_profile[key] = value

    return {
        "sources": sources,
        "legacy_profile": merged_profile,
    }


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
            return "continuar_conversacion"
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
        return "continuar_conversacion"
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
        "clinica",
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
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False
    if normalized in NEGATIVE_TOKENS:
        return True

    words = normalized.split()
    if not words:
        return False

    if words[0] == "no" or normalized.startswith("no "):
        return True

    return any(
        token in normalized
        for token in (
            "cambiar",
            "cambia",
            "incorrect",
            "ajustar",
            "cancelar",
            "cancel",
            "anular",
            "ya no quiero",
            "detener",
            "suspender",
        )
    )


def is_no_thanks_message(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    no_thanks_patterns = (
        "no gracias",
        "gracias no",
        "no muchas gracias",
        "todo bien gracias",
        "eso es todo",
        "eso era todo",
        "nada mas gracias",
        "ninguna otra consulta",
    )
    return any(pattern in normalized for pattern in no_thanks_patterns)


def is_route_cancellation_request(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    route_markers = (
        "ruta",
        "program",
        "retiro",
        "recogida",
        "recoleccion",
        "muestra",
        "domicilio",
    )
    has_cancel_marker = any(
        token in normalized
        for token in (
            "cancel",
            "cancelar",
            "anular",
            "ya no quiero program",
            "ya no quiero agendar",
            "detener",
            "suspender",
        )
    )
    has_route_marker = any(token in normalized for token in route_markers)
    return has_cancel_marker and has_route_marker


def is_client_identity_mismatch_reply(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    mismatch_patterns = (
        "no es mi veterinaria",
        "no es mi clinica",
        "ese no es mi cliente",
        "cliente incorrect",
        "veterinaria incorrect",
        "registro incorrect",
        "te equivocaste de cliente",
        "no corresponde",
        "es otra veterinaria",
        "es otro cliente",
    )
    if any(pattern in normalized for pattern in mismatch_patterns):
        return True

    return "cliente" in normalized and "incorrect" in normalized


def is_catalog_symptom_followup(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    symptom_markers = ("sintoma", "sintomas", "signo", "signos", "malestar")
    exam_markers = (
        "examen",
        "analisis",
        "prueba",
        "que examen",
        "cual examen",
        "se le puede hacer",
        "se le puede realizar",
        "que le puedo mandar",
    )
    patient_markers = ("perro", "gato", "mascota", "paciente")

    has_symptom_marker = any(token in normalized for token in symptom_markers)
    has_exam_or_patient_context = any(token in normalized for token in exam_markers) or any(
        token in normalized for token in patient_markers
    )
    return has_symptom_marker and has_exam_or_patient_context


def build_catalog_follow_up_reply(text: str) -> str:
    if is_catalog_symptom_followup(text):
        return (
            "Claro, puedes compartirme los sintomas. "
            "Con especie, edad aproximada y sintomas principales te oriento sobre el examen mas util, "
            "toma de muestra y valor referencial."
        )

    return (
        "Para orientarte mejor, comparteme el nombre exacto del examen o el tipo de muestra "
        "(por ejemplo sangre, orina o heces) y te doy valor referencial, toma y tiempo estimado."
    )


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

    prefix = "Perfecto" if audience == "profesional" else "Claro"
    exam_label = f"{test_name} (codigo {code})" if code else test_name
    response_parts = [f"{prefix}, en nuestros servicios de laboratorio, para {exam_label} del grupo {clinical_group}"]

    if sample_group != "no especificado":
        response_parts.append(f"la muestra base es {sample_group}")
    if collection_note:
        response_parts.append(f"la toma recomendada es {collection_note}")
    if price_label and wants_price:
        response_parts.append(f"el valor referencial es {price_label}")
    elif not wants_price and price_label:
        response_parts.append(f"si lo necesitas, su valor referencial es {price_label}")
    if turnaround_label:
        response_parts.append(f"y el tiempo estimado es {turnaround_label}")

    message = ", ".join(response_parts).strip() + "."
    if audience == "profesional":
        return f"{message} Si quieres, te paso alternativas del mismo grupo diagnostico."
    return f"{message} Si deseas, te ayudo a elegir la opcion mas adecuada segun el caso."


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
            f"Perfecto, manejamos servicios para {sample_label} con pruebas en {group_label}, {price_span}. "
            f"Por ejemplo, {examples_label}, con tiempo estimado de referencia {turnaround_label}. "
            "Si me indicas el objetivo clinico, te priorizo el panel mas util."
        )

    return (
        f"Claro, manejamos servicios para {sample_label} y tenemos examenes de {group_label}, {price_span}. "
        f"Por ejemplo, {examples_label}, con tiempo estimado de referencia {turnaround_label}. "
        "Si me dices el examen exacto o codigo, te doy valor referencial y toma de muestra."
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

    if is_catalog_symptom_followup(text):
        return build_catalog_follow_up_reply(text)

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
            "Puedo ayudarte con los servicios del laboratorio y precios aproximados. "
            "En este momento no tengo cargado el catalogo detallado, pero si me dices el examen te oriento."
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
            return f"{grouped_reply} Si buscas un precio puntual, comparteme el nombre exacto o el codigo del examen."
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
            f"Claro, manejamos servicios como {category_label}. "
            f"Por ejemplo, {sample_label}. Si me dices el examen exacto o el tipo de muestra, te comparto valor referencial, toma de muestra y tiempo estimado."
        )

    return (
        "Claro, puedo orientarte con los servicios del laboratorio. "
        "Si me dices el examen exacto o codigo, te comparto valor referencial en COP y tiempo estimado."
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


def build_tax_id_lookup_keys(value: str) -> set[str]:
    raw = (value or "").strip()
    if not raw:
        return set()

    normalized = normalize_tax_id(raw)
    if not normalized:
        return set()

    keys = {normalized}

    hyphen_match = re.match(r"^\s*([A-Za-z0-9]+)\s*[-]\s*([A-Za-z0-9])\s*$", raw)
    if hyphen_match:
        base = normalize_tax_id(hyphen_match.group(1))
        dv = normalize_tax_id(hyphen_match.group(2))
        if base:
            keys.add(base)
            if dv:
                keys.add(f"{base}{dv}")
    elif normalized.isdigit() and len(normalized) >= 8:
        keys.add(normalized[:-1])

    return {key for key in keys if len(key) >= 5}


def tax_id_match_score(input_tax_id: str, candidate_tax_id: str) -> float:
    input_normalized = normalize_tax_id(input_tax_id)
    candidate_normalized = normalize_tax_id(candidate_tax_id)
    if not input_normalized or not candidate_normalized:
        return 0.0

    if input_normalized == candidate_normalized:
        return 1.0

    input_keys = build_tax_id_lookup_keys(input_tax_id)
    candidate_keys = build_tax_id_lookup_keys(candidate_tax_id)
    shared_keys = input_keys.intersection(candidate_keys)
    if not shared_keys:
        return 0.0

    longest_shared = max(len(item) for item in shared_keys)
    score = min(0.95, 0.72 + (longest_shared / 100.0))

    if input_normalized.isdigit() and candidate_normalized.isdigit():
        if input_normalized[:-1] == candidate_normalized or candidate_normalized[:-1] == input_normalized:
            score = max(score, 0.9)

    return score


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


def extract_accounting_invoice_candidate(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    tagged = re.search(
        r"(?:factura|recibo|comprobante|cuenta)\s*(?:numero|nro|no|#)?\s*[:#-]?\s*([A-Za-z0-9-]{4,24})",
        raw,
        flags=re.IGNORECASE,
    )
    if tagged:
        return tagged.group(1).strip()

    if re.fullmatch(r"[A-Za-z0-9-]{5,24}", raw) and any(char.isdigit() for char in raw):
        return raw

    return None


def extract_accounting_period_candidate(text: str) -> str | None:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return None

    month_match = re.search(
        r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
        normalized,
    )
    if month_match:
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        if year_match:
            return f"{month_match.group(1)} {year_match.group(1)}"
        return month_match.group(1)

    period_match = re.search(
        r"\b(?:periodo|mes|corte|quincena|trimestre)\b[^\n]{0,24}",
        normalized,
    )
    if period_match:
        return period_match.group(0).strip()

    return None


def should_apply_accounting_guard(*, session: dict[str, Any] | None, text: str, reply: str) -> bool:
    normalized = normalize_text_value(text)
    if not normalized:
        return False

    if extract_tax_id_candidate(text):
        return True
    if extract_accounting_period_candidate(text):
        return True

    invoice_candidate = extract_accounting_invoice_candidate(text)
    if invoice_candidate:
        return True

    if re.fullmatch(r"\d{5,20}", normalized):
        return True

    previous_bot_message = ((session or {}).get("last_bot_message") or "").strip().lower()
    current_reply = (reply or "").strip().lower()
    if previous_bot_message and previous_bot_message == current_reply and "contabilidad" in current_reply:
        return True

    return False


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


def is_probable_clinic_name_input(text: str) -> bool:
    normalized = normalize_lookup_key(text)
    if not normalized:
        return False

    strong_markers = (
        "veterinaria",
        "clinica",
        "nombre fiscal",
        "nombre de la veterinaria",
    )
    if any(marker in normalized for marker in strong_markers):
        return True

    tokens = [token for token in normalized.split() if token]
    if not tokens or len(tokens) > 3:
        return False

    blocked_tokens = {
        "a",
        "al",
        "como",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "la",
        "las",
        "lo",
        "los",
        "me",
        "mi",
        "mis",
        "por",
        "que",
        "se",
        "si",
        "tal",
        "tu",
        "un",
        "una",
        "y",
        "hola",
        "buenas",
        "buenos",
        "dias",
        "tardes",
        "ayudame",
        "ayudan",
        "ayudas",
        "necesito",
        "quiero",
        "programar",
        "agendar",
        "ruta",
        "retiro",
        "recogida",
        "recoleccion",
        "muestra",
        "muestras",
        "servicio",
        "servicios",
        "precio",
        "costos",
        "analisis",
        "examen",
        "resultado",
        "resultados",
        "contabilidad",
        "pqrs",
        "consulta",
        "ayuda",
        "menu",
        "opcion",
    }

    if all(token in blocked_tokens for token in tokens):
        return False

    if len(tokens) == 1:
        single = tokens[0]
        if single.isdigit():
            return False
        return len(single) >= 4

    meaningful_tokens = [
        token
        for token in tokens
        if token not in blocked_tokens and not token.isdigit() and len(token) >= 3
    ]
    return bool(meaningful_tokens)


def clinic_name_similarity_score(query_name: str, candidate_name: str) -> float:
    query = normalize_lookup_key(query_name)
    candidate = normalize_lookup_key(candidate_name)
    if not query or not candidate:
        return 0.0

    if query == candidate:
        return 1.0

    query_tokens = [token for token in query.split() if token]
    candidate_tokens = [token for token in candidate.split() if token]
    token_overlap = 0.0
    if query_tokens and candidate_tokens:
        intersection = set(query_tokens).intersection(candidate_tokens)
        token_overlap = len(intersection) / max(len(set(query_tokens)), len(set(candidate_tokens)))

    containment_bonus = 0.0
    if query in candidate or candidate in query:
        containment_bonus = min(len(query), len(candidate)) / max(len(query), len(candidate))

    sequence_ratio = SequenceMatcher(None, query, candidate).ratio()
    combined = (token_overlap * 0.75) + (containment_bonus * 0.25)
    return max(sequence_ratio, combined)


def is_reasonable_clinic_match(query_name: str, candidate_name: str, score: float) -> bool:
    query = normalize_lookup_key(query_name)
    candidate = normalize_lookup_key(candidate_name)
    if not query or not candidate:
        return False

    if query == candidate or score >= 0.9:
        return True

    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    overlap_count = len(query_tokens.intersection(candidate_tokens))

    if overlap_count >= 2 and score >= 0.72:
        return True
    if overlap_count >= 1 and score >= 0.82:
        return True
    if len(query_tokens) == 1 and len(candidate_tokens) == 1 and score >= 0.8:
        return True

    return False


def select_best_clinic_candidate(clinic_hint: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        name = str(row.get("clinic_name") or "").strip()
        if not name:
            continue
        score = clinic_name_similarity_score(clinic_hint, name)
        if score > 0:
            ranked.append((score, row))

    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best_row = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0

    if not is_reasonable_clinic_match(clinic_hint, str(best_row.get("clinic_name") or ""), best_score):
        return None

    if len(ranked) > 1 and best_score < 0.9 and (best_score - second_score) < 0.06:
        return None

    return dict(best_row)


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


def client_candidate_signature(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("id") or "").strip()
    if candidate_id:
        return f"id:{candidate_id}"
    clinic_key = normalize_lookup_key(str(candidate.get("clinic_name") or ""))
    tax_key = normalize_tax_id(str(candidate.get("tax_id") or ""))
    return f"key:{clinic_key}|{tax_key}"


def append_unique_client_candidate(
    bucket: list[dict[str, Any]],
    seen_signatures: set[str],
    candidate: dict[str, Any],
) -> None:
    if not isinstance(candidate, dict):
        return
    signature = client_candidate_signature(candidate)
    if signature in seen_signatures:
        return
    seen_signatures.add(signature)
    bucket.append(dict(candidate))


def enrich_client_address_with_knowledge(client_row: dict[str, Any], clinic_hint: str) -> dict[str, Any]:
    enriched = dict(client_row)
    if is_meaningful_value(enriched.get("address")):
        return enriched

    search_a3_knowledge = getattr(supabase, "search_a3_knowledge_by_clinic_name", None)
    if not callable(search_a3_knowledge):
        return enriched

    try:
        knowledge_rows = ensure_dict_rows(search_a3_knowledge(clinic_hint, limit=1))
    except httpx.HTTPStatusError:
        knowledge_rows = []

    if knowledge_rows:
        enriched["address"] = knowledge_rows[0].get("address")

    return enriched


def find_registered_client_by_tax_id(tax_id: str) -> dict[str, Any] | None:
    lookup_keys = build_tax_id_lookup_keys(tax_id)
    if not lookup_keys:
        return None

    candidates: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    get_client_by_tax_id = getattr(supabase, "get_client_by_tax_id", None)
    if callable(get_client_by_tax_id):
        for key in lookup_keys:
            try:
                row = get_client_by_tax_id(key)
            except httpx.HTTPStatusError:
                row = None
            if isinstance(row, dict):
                append_unique_client_candidate(candidates, seen_signatures, row)

    search_clients_by_tax_id = getattr(supabase, "search_clients_by_tax_id", None)
    if callable(search_clients_by_tax_id):
        for key in lookup_keys:
            try:
                rows = ensure_dict_rows(search_clients_by_tax_id(key, limit=12))
            except httpx.HTTPStatusError:
                rows = []
            for row in rows:
                append_unique_client_candidate(candidates, seen_signatures, row)

    if not candidates:
        list_clients = getattr(supabase, "list_clients_with_assignment", None)
        if callable(list_clients):
            try:
                rows = ensure_dict_rows(list_clients())
            except httpx.HTTPStatusError:
                rows = []
            for row in rows:
                append_unique_client_candidate(candidates, seen_signatures, row)

    best_client: dict[str, Any] | None = None
    best_score = 0.0
    for candidate in candidates:
        score = tax_id_match_score(tax_id, str(candidate.get("tax_id") or ""))
        if score > best_score:
            best_score = score
            best_client = dict(candidate)

    if best_client and best_score >= 0.75:
        clinic_hint = str(best_client.get("clinic_name") or "")
        return enrich_client_address_with_knowledge(best_client, clinic_hint)

    return None


def find_registered_client_by_clinic_name(clinic_hint: str) -> dict[str, Any] | None:
    if not clinic_hint:
        return None
    if not is_probable_clinic_name_input(clinic_hint):
        return None

    candidates: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    search_by_name = getattr(supabase, "search_clients_by_clinic_name", None)
    if callable(search_by_name):
        try:
            rows = ensure_dict_rows(search_by_name(clinic_hint, limit=12))
        except httpx.HTTPStatusError:
            rows = []
        for row in rows:
            append_unique_client_candidate(candidates, seen_signatures, row)

    if len(candidates) < 3:
        list_clients = getattr(supabase, "list_clients_with_assignment", None)
        if callable(list_clients):
            try:
                rows = ensure_dict_rows(list_clients())
            except httpx.HTTPStatusError:
                rows = []
            for row in rows:
                append_unique_client_candidate(candidates, seen_signatures, row)

    best_candidate = select_best_clinic_candidate(clinic_hint, candidates)
    if best_candidate:
        return enrich_client_address_with_knowledge(best_candidate, clinic_hint)

    search_a3_knowledge = getattr(supabase, "search_a3_knowledge_by_clinic_name", None)
    if callable(search_a3_knowledge):
        try:
            knowledge_rows = ensure_dict_rows(search_a3_knowledge(clinic_hint, limit=10))
        except httpx.HTTPStatusError:
            knowledge_rows = []

        best_knowledge = select_best_clinic_candidate(clinic_hint, knowledge_rows)
        if best_knowledge:
            return {
                "id": None,
                "clinic_name": best_knowledge.get("clinic_name"),
                "phone": best_knowledge.get("phone"),
                "tax_id": None,
                "address": best_knowledge.get("address"),
                "clinic_key": best_knowledge.get("clinic_key"),
                "is_registered": bool(best_knowledge.get("is_registered", False)),
                "is_new_client": bool(best_knowledge.get("is_new_client", False)),
            }

    return None


def identify_client_by_tax_id_or_clinic(incoming_text: str) -> dict[str, Any] | None:
    tax_id = extract_tax_id_candidate(incoming_text)
    if tax_id:
        client_by_tax = find_registered_client_by_tax_id(tax_id)
        if client_by_tax:
            return client_by_tax

    clinic_hint = extract_clinic_name_hint(incoming_text)
    if clinic_hint:
        client_by_name = find_registered_client_by_clinic_name(clinic_hint)
        if client_by_name:
            return client_by_name

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


def build_demo_locality_coverage_from_assignments(
    *,
    clients_rows: list[dict[str, Any]],
    couriers_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    courier_index: dict[str, dict[str, Any]] = {}
    for row in couriers_rows:
        courier_id = str(row.get("id") or "").strip()
        courier_name = str(row.get("name") or "").strip()
        if not courier_id or not courier_name:
            continue
        courier_index[courier_id] = row

    if not courier_index:
        return []

    locality_votes: dict[str, Counter[str]] = {}
    for client in clients_rows:
        locality = resolve_bogota_locality(client.get("zone") or client.get("city"))
        if not locality:
            continue

        assignment = assignment_from_client(client)
        if not isinstance(assignment, dict):
            continue

        courier_id = str(assignment.get("courier_id") or "").strip()
        if not courier_id:
            courier_payload = assignment.get("couriers")
            if isinstance(courier_payload, dict):
                courier_id = str(courier_payload.get("id") or "").strip()

        if courier_id not in courier_index:
            continue

        locality_votes.setdefault(locality["code"], Counter())[courier_id] += 1

    ordered_courier_ids = sorted(
        courier_index.keys(),
        key=lambda courier_id: normalize_lookup_key(
            str(courier_index[courier_id].get("name") or "")
        ),
    )
    if not ordered_courier_ids:
        return []

    now_iso = datetime.now().isoformat()
    demo_rows: list[dict[str, Any]] = []
    for index, locality in enumerate(BOGOTA_LOCALITIES):
        locality_code = locality["code"]
        vote_counter = locality_votes.get(locality_code)
        if vote_counter:
            selected_courier_id = vote_counter.most_common(1)[0][0]
        else:
            selected_courier_id = ordered_courier_ids[index % len(ordered_courier_ids)]

        courier_row = courier_index.get(selected_courier_id, {})
        demo_rows.append(
            {
                "locality_code": locality_code,
                "locality_name": locality["name"],
                "courier_id": selected_courier_id,
                "assigned_by": "dashboard_demo_video",
                "assigned_at": now_iso,
                "couriers": {
                    "id": selected_courier_id,
                    "name": courier_row.get("name"),
                    "phone": courier_row.get("phone"),
                    "availability": courier_row.get("availability") or "available",
                },
            }
        )

    return demo_rows


def format_turnaround_label(hours: int | None) -> str:
    if not hours:
        return "Por definir"
    if hours % 24 == 0:
        days = hours // 24
        return f"{days} dia(s)"
    return f"{hours} hora(s)"


def normalize_status_value(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_request_priority_value(value: Any) -> str:
    normalized = normalize_lookup_key(str(value or ""))
    if not normalized:
        return ""
    if normalized in {"normal", "estandar", "standar", "media", "medio", "baja", "bajo"}:
        return "normal"
    if normalized in {"alta", "high", "prioridadalta"}:
        return "high"
    if normalized in {"urgente", "urgent", "critica", "critico", "prioridadurgente"}:
        return "urgent"
    if normalized in REQUEST_PRIORITY_LABELS:
        return normalized
    return ""


def normalize_request_priority_db_value(priority: str) -> str:
    return REQUEST_PRIORITY_DB_MAP.get(priority, "normal")


def normalize_uuid_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        text,
    ):
        return ""
    return text


def normalize_sample_status_db_value(status: str) -> str:
    normalized = normalize_status_value(status)
    if normalized in SAMPLE_STATUS_DB_OPTIONS:
        return normalized
    return SAMPLE_STATUS_DB_FALLBACK.get(normalized, "pending_pickup")


def normalize_request_sample_count_value(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d{1,3}", text):
        return None
    count = int(text)
    if count < 0 or count > 999:
        return None
    return count


def sanitize_sample_type_value(value: Any, max_length: int = 80) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    if len(text) > max_length:
        text = text[:max_length].strip()
    return text


def normalize_request_sample_types_value(value: Any) -> list[str]:
    if value is None:
        return []

    raw_items: list[Any]
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif isinstance(value, str):
        raw_items = [part.strip() for part in re.split(r"[;,]", value)]
    else:
        raw_items = [value]

    seen: set[str] = set()
    cleaned: list[str] = []
    for raw_item in raw_items:
        sample_type = sanitize_sample_type_value(raw_item)
        sample_type_key = normalize_lookup_key(sample_type)
        if not sample_type or not sample_type_key or sample_type_key in seen:
            continue
        cleaned.append(sample_type)
        seen.add(sample_type_key)
        if len(cleaned) >= 12:
            break

    return cleaned


def parse_request_manual_overrides(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}
    for row in events:
        request_id = str(row.get("request_id") or "").strip()
        if not request_id or request_id in overrides:
            continue

        payload = row.get("event_payload")
        if not isinstance(payload, dict):
            continue

        override: dict[str, Any] = {}
        priority = normalize_request_priority_value(payload.get("priority"))
        if priority:
            override["priority"] = priority

        if "sample_count" in payload:
            sample_count = normalize_request_sample_count_value(payload.get("sample_count"))
            if sample_count is not None:
                override["sample_count"] = sample_count

        if "sample_types" in payload:
            override["sample_types"] = normalize_request_sample_types_value(
                payload.get("sample_types")
            )

        if override:
            overrides[request_id] = override

    return overrides


def parse_sample_manual_status_overrides(events: list[dict[str, Any]]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for row in events:
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id or sample_id in overrides:
            continue

        payload = row.get("event_payload")
        if not isinstance(payload, dict):
            continue

        status = normalize_status_value(payload.get("status"))
        if status in SAMPLE_STATUS_LABELS:
            overrides[sample_id] = status

    return overrides


def build_dashboard_context() -> dict[str, Any]:
    clients = safe_fetch(supabase.list_clients_with_assignment, [])
    knowledge_index = safe_fetch(lambda: supabase.list_a3_knowledge_index(limit=5000), [])
    knowledge_profile_schema_probe = safe_fetch(
        lambda: supabase.fetch_rows(
            "clients_a3_knowledge",
            {"select": "billing_email", "limit": "1"},
        ),
        None,
    )
    professionals_index = safe_fetch(
        lambda: supabase.list_a3_professionals_index(limit=8000),
        [],
    )
    couriers = safe_fetch(lambda: supabase.list_active_couriers(limit=2000), [])
    locality_coverage_fetch_status = 200
    try:
        locality_coverage = supabase.list_courier_locality_coverage(limit=400)
    except httpx.HTTPStatusError as exc:
        locality_coverage = []
        locality_coverage_fetch_status = exc.response.status_code
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
                "select": "id,request_id,client_id,status,priority,test_code,test_name,sample_type,created_at,estimated_ready_at,delivered_at,clients(clinic_name),couriers(name)",
                "order": "created_at.desc",
                "limit": "4000",
            },
        ),
        [],
    )
    request_manual_events = safe_fetch(
        lambda: supabase.fetch_rows(
            "request_events",
            {
                "select": "request_id,event_payload,created_at",
                "event_type": "eq.dashboard_request_manual_update",
                "order": "created_at.desc",
                "limit": "8000",
            },
        ),
        [],
    )
    sample_manual_events = safe_fetch(
        lambda: supabase.fetch_rows(
            "lab_sample_events",
            {
                "select": "sample_id,event_payload,created_at",
                "event_type": "eq.dashboard_status_update",
                "order": "created_at.desc",
                "limit": "8000",
            },
        ),
        [],
    )

    request_manual_overrides = parse_request_manual_overrides(
        ensure_dict_rows(request_manual_events)
    )
    sample_manual_status_overrides = parse_sample_manual_status_overrides(
        ensure_dict_rows(sample_manual_events)
    )
    effective_samples: list[dict[str, Any]] = []
    for raw_sample in ensure_dict_rows(samples):
        sample_row = dict(raw_sample)
        sample_id = str(sample_row.get("id") or "").strip()
        override_status = sample_manual_status_overrides.get(sample_id)
        if override_status:
            sample_row["status"] = override_status
        effective_samples.append(sample_row)
    samples = effective_samples

    total_clients = len(clients)
    clients_with_courier = 0
    courier_counter: Counter[str] = Counter()
    zone_counter: Counter[str] = Counter()
    locality_client_counter: Counter[str] = Counter()
    locality_clients_by_courier_counter: Counter[str] = Counter()
    request_count_by_client: Counter[str] = Counter()
    sample_count_by_client: Counter[str] = Counter()
    latest_request_by_client: dict[str, str] = {}
    latest_sample_by_client: dict[str, str] = {}
    sample_count_by_request: Counter[str] = Counter()
    latest_sample_status_by_request: dict[str, str] = {}
    sample_types_by_request: dict[str, set[str]] = {}
    sample_type_option_set: set[str] = set()

    knowledge_rows = ensure_dict_rows(knowledge_index)
    professionals_rows = ensure_dict_rows(professionals_index)
    courier_rows = ensure_dict_rows(couriers)
    knowledge_profile_extended_schema = knowledge_profile_schema_probe is not None
    knowledge_profile_editing_enabled = True
    knowledge_profile_compat_mode = not knowledge_profile_extended_schema
    knowledge_by_key: dict[str, dict[str, Any]] = {}
    knowledge_by_name: dict[str, dict[str, Any]] = {}
    knowledge_by_phone: dict[str, dict[str, Any]] = {}

    for row in knowledge_rows:
        clinic_key = str(row.get("clinic_key") or "").strip()
        if clinic_key and clinic_key not in knowledge_by_key:
            knowledge_by_key[clinic_key] = row

        clinic_name_key = normalize_lookup_key(str(row.get("clinic_name") or ""))
        if clinic_name_key and clinic_name_key not in knowledge_by_name:
            knowledge_by_name[clinic_name_key] = row

        phone_key = normalize_phone_lookup(row.get("phone"))
        if phone_key and phone_key not in knowledge_by_phone:
            knowledge_by_phone[phone_key] = row

    professionals_by_clinic_key: dict[str, list[dict[str, Any]]] = {}
    for row in professionals_rows:
        clinic_key = str(row.get("clinic_key") or "").strip()
        if not clinic_key:
            continue
        professionals_by_clinic_key.setdefault(clinic_key, []).append(row)

    def resolve_client_knowledge(client_row: dict[str, Any]) -> dict[str, Any] | None:
        clinic_name_key = normalize_lookup_key(str(client_row.get("clinic_name") or ""))
        if clinic_name_key and clinic_name_key in knowledge_by_key:
            return knowledge_by_key[clinic_name_key]

        phone_key = normalize_phone_lookup(client_row.get("phone"))
        if phone_key and phone_key in knowledge_by_phone:
            return knowledge_by_phone[phone_key]

        if clinic_name_key and clinic_name_key in knowledge_by_name:
            return knowledge_by_name[clinic_name_key]

        return None

    couriers_options = []
    for row in courier_rows:
        courier_id = str(row.get("id") or "").strip()
        courier_name = str(row.get("name") or "").strip()
        if not courier_id or not courier_name:
            continue
        couriers_options.append(
            {
                "id": courier_id,
                "name": courier_name,
                "phone": row.get("phone") or "-",
                "availability": row.get("availability") or "available",
                "color": courier_color_for_id(courier_id),
            }
        )

    couriers_options.sort(key=lambda row: str(row.get("name") or ""))

    locality_coverage_demo_mode = False
    locality_coverage_demo_reason = ""
    locality_coverage_rows = ensure_dict_rows(locality_coverage)
    if not locality_coverage_rows and locality_coverage_fetch_status == 404:
        locality_coverage_rows = build_demo_locality_coverage_from_assignments(
            clients_rows=ensure_dict_rows(clients),
            couriers_rows=courier_rows,
        )
        if locality_coverage_rows:
            locality_coverage_demo_mode = True
            locality_coverage_demo_reason = "coverage_table_missing"

    locality_coverage_by_code: dict[str, dict[str, Any]] = {}
    locality_coverage_by_name: dict[str, dict[str, Any]] = {}
    localities_by_courier: dict[str, list[str]] = {}
    for row in locality_coverage_rows:
        locality_code = normalize_locality_code(row.get("locality_code"))
        locality_name = str(row.get("locality_name") or "").strip()
        if locality_code and locality_code not in locality_coverage_by_code:
            locality_coverage_by_code[locality_code] = row
        locality_name_key = normalize_lookup_key(locality_name)
        if locality_name_key and locality_name_key not in locality_coverage_by_name:
            locality_coverage_by_name[locality_name_key] = row

        courier_id = str(row.get("courier_id") or "").strip()
        if courier_id and locality_name:
            localities_by_courier.setdefault(courier_id, []).append(locality_name)

    localities_rows: list[dict[str, Any]] = []
    coverage_map_points: list[dict[str, Any]] = []
    for locality in BOGOTA_LOCALITIES:
        locality_code = locality["code"]
        coverage_row = locality_coverage_by_code.get(locality_code)
        if not coverage_row:
            coverage_row = locality_coverage_by_name.get(normalize_lookup_key(locality["name"]))

        courier_payload = (
            coverage_row.get("couriers")
            if isinstance(coverage_row, dict) and isinstance(coverage_row.get("couriers"), dict)
            else {}
        )
        assigned_courier_id = str(
            ((coverage_row or {}).get("courier_id") if isinstance(coverage_row, dict) else "")
            or courier_payload.get("id")
            or ""
        ).strip()
        assigned_courier_name = str(courier_payload.get("name") or "").strip()

        point_color = courier_color_for_id(assigned_courier_id)
        if not assigned_courier_id:
            point_color = "#475569"

        localities_rows.append(
            {
                "locality_code": locality_code,
                "locality_name": locality["name"],
                "assigned_courier_id": assigned_courier_id,
                "assigned_courier_name": assigned_courier_name or "Sin asignar",
                "assigned_courier_phone": str(courier_payload.get("phone") or "").strip(),
                "is_assigned": bool(assigned_courier_id),
                "coverage_state": "assigned" if assigned_courier_id else "pending",
                "map_color": point_color,
            }
        )
        coverage_map_points.append(
            {
                "locality_code": locality_code,
                "locality_name": locality["name"],
                "lat": locality["lat"],
                "lng": locality["lng"],
                "courier_id": assigned_courier_id,
                "courier_name": assigned_courier_name or "Sin asignar",
                "color": point_color,
                "is_assigned": bool(assigned_courier_id),
            }
        )

    localities_rows.sort(key=lambda row: str(row.get("locality_name") or ""))

    couriers_rows: list[dict[str, Any]] = []
    for courier in couriers_options:
        courier_id = str(courier.get("id") or "").strip()
        assigned_localities = sorted(
            localities_by_courier.get(courier_id, []),
            key=normalize_lookup_key,
        )
        couriers_rows.append(
            {
                "id": courier_id,
                "name": courier.get("name") or "-",
                "phone": str(courier.get("phone") or "").strip(),
                "availability": courier.get("availability") or "available",
                "color": courier.get("color") or courier_color_for_id(courier_id),
                "coverage_count": len(assigned_localities),
                "clients_count_from_coverage": locality_clients_by_courier_counter.get(courier_id, 0),
                "phone_missing": not bool(normalize_phone_lookup(courier.get("phone"))),
                "localities": assigned_localities,
                "localities_text": ", ".join(assigned_localities)
                if assigned_localities
                else "Sin zonas asignadas",
            }
        )

    clients_by_id = {
        str(client.get("id") or "").strip(): client
        for client in ensure_dict_rows(clients)
        if str(client.get("id") or "").strip()
    }

    for catalog_row in ensure_dict_rows(catalog):
        sample_type = sanitize_sample_type_value(catalog_row.get("sample_type"))
        if sample_type:
            sample_type_option_set.add(sample_type)

    for sample_row in ensure_dict_rows(samples):
        sample_type = sanitize_sample_type_value(sample_row.get("sample_type"))
        if sample_type:
            sample_type_option_set.add(sample_type)

    for override in request_manual_overrides.values():
        for sample_type in normalize_request_sample_types_value(override.get("sample_types")):
            sample_type_option_set.add(sample_type)

    for client in clients:
        knowledge_row = resolve_client_knowledge(client) or {}
        zone = (
            client.get("zone")
            or knowledge_row.get("locality")
            or "Sin zona"
        ).strip()
        zone_counter[zone] += 1
        locality = resolve_bogota_locality(zone)
        if locality:
            locality_client_counter[locality["code"]] += 1

        assignment = assignment_from_client(client)

        if assignment:
            clients_with_courier += 1
            courier_data = assignment.get("couriers")
            courier_name = courier_data.get("name") if courier_data else "Sin mensajero"
            courier_counter[courier_name or "Sin mensajero"] += 1

    for locality_row in localities_rows:
        locality_code = str(locality_row.get("locality_code") or "")
        clients_in_locality = locality_client_counter.get(locality_code, 0)
        locality_row["clients_count"] = clients_in_locality

        assigned_courier_id = str(locality_row.get("assigned_courier_id") or "").strip()
        if assigned_courier_id:
            locality_clients_by_courier_counter[assigned_courier_id] += clients_in_locality

    for map_point in coverage_map_points:
        locality_code = str(map_point.get("locality_code") or "")
        map_point["clients_count"] = locality_client_counter.get(locality_code, 0)

    for courier_row in couriers_rows:
        courier_id = str(courier_row.get("id") or "").strip()
        courier_row["clients_count_from_coverage"] = locality_clients_by_courier_counter.get(
            courier_id,
            0,
        )

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
            client_id_text = ""
        else:
            client_id_text = str(client_id)
            sample_count_by_client[client_id_text] += 1
            if client_id_text not in latest_sample_by_client:
                latest_sample_by_client[client_id_text] = row.get("status") or "-"

        request_id = str(row.get("request_id") or "").strip()
        if request_id:
            sample_count_by_request[request_id] += 1
            if request_id not in latest_sample_status_by_request:
                latest_sample_status_by_request[request_id] = row.get("status") or "-"

            sample_type = str(row.get("sample_type") or "").strip()
            if sample_type:
                sample_types_by_request.setdefault(request_id, set()).add(sample_type)

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
    clients_with_knowledge = 0
    clients_marked_new = 0
    for client in clients:
        assignment = assignment_from_client(client)
        courier_data = assignment.get("couriers") if assignment else None
        client_id = str(client.get("id") or "").strip()
        knowledge_row = resolve_client_knowledge(client) or {}
        _, legacy_profile = parse_knowledge_sources_payload(knowledge_row.get("sources_json"))

        clinic_name = str(client.get("clinic_name") or knowledge_row.get("clinic_name") or "-").strip()
        clinic_key = str(knowledge_row.get("clinic_key") or normalize_lookup_key(clinic_name)).strip()
        commercial_name = str(
            knowledge_row.get("commercial_name") or legacy_profile.get("commercial_name") or ""
        ).strip()

        display_name = commercial_name or clinic_name
        clinic_name_norm = normalize_lookup_key(clinic_name)
        commercial_name_norm = normalize_lookup_key(commercial_name)
        secondary_name = "-"
        if commercial_name and clinic_name and commercial_name_norm != clinic_name_norm:
            secondary_name = clinic_name

        professional_rows = professionals_by_clinic_key.get(clinic_key, [])
        professional_names = sorted(
            {
                str(row.get("professional_name") or "").strip()
                for row in professional_rows
                if str(row.get("professional_name") or "").strip()
            }
        )
        professional_cards = sorted(
            {
                str(row.get("professional_card") or "").strip()
                for row in professional_rows
                if str(row.get("professional_card") or "").strip()
            }
        )

        professional_name_text = ", ".join(professional_names[:2]) if professional_names else "-"
        if len(professional_names) > 2:
            professional_name_text = (
                f"{professional_name_text} (+{len(professional_names) - 2})"
            )

        professional_card_text = ", ".join(professional_cards[:2]) if professional_cards else "-"
        if len(professional_cards) > 2:
            professional_card_text = (
                f"{professional_card_text} (+{len(professional_cards) - 2})"
            )

        assigned_courier_id = str(
            (assignment or {}).get("courier_id")
            or (courier_data.get("id") if isinstance(courier_data, dict) else "")
            or ""
        ).strip()

        billing_type = str(client.get("billing_type") or "").strip().lower()
        if billing_type == "credit":
            billing_type_label = "Credito"
        elif billing_type == "cash":
            billing_type_label = "Contado"
        else:
            billing_type_label = "-"

        has_knowledge = bool(knowledge_row)
        is_registered = bool(knowledge_row.get("is_registered")) if has_knowledge else False
        is_new_client = bool(knowledge_row.get("is_new_client")) if has_knowledge else False

        if has_knowledge:
            clients_with_knowledge += 1
        if is_new_client:
            clients_marked_new += 1

        registration_state = "Sin indice"
        if is_new_client:
            registration_state = "Nuevo"
        elif is_registered:
            registration_state = "Registrado"
        elif has_knowledge:
            registration_state = "No confirmado"

        client_type_value = normalize_client_type_value(
            knowledge_row.get("client_type") or legacy_profile.get("client_type")
        )
        vat_regime_value = normalize_vat_regime_value(
            knowledge_row.get("vat_regime") or legacy_profile.get("vat_regime")
        )
        electronic_invoicing_value = normalize_bool_option_value(
            knowledge_row.get("electronic_invoicing")
            if knowledge_row.get("electronic_invoicing") is not None
            else legacy_profile.get("electronic_invoicing")
        )
        entered_flag_value = normalize_bool_option_value(
            knowledge_row.get("entered_flag")
            if knowledge_row.get("entered_flag") is not None
            else legacy_profile.get("entered_flag")
        )

        registration_timestamp = str(
            knowledge_row.get("registration_timestamp")
            or legacy_profile.get("registration_timestamp")
            or knowledge_row.get("source_updated_at")
            or knowledge_row.get("synced_at")
            or client.get("created_at")
            or ""
        ).strip()
        registration_date = str(
            knowledge_row.get("registration_date") or legacy_profile.get("registration_date") or ""
        ).strip()
        registration_time = str(
            knowledge_row.get("registration_time") or legacy_profile.get("registration_time") or ""
        ).strip()
        if not registration_date and registration_timestamp:
            registration_date = registration_timestamp[:10]
        if not registration_time and len(registration_timestamp) >= 16:
            registration_time = registration_timestamp[11:16]

        clients_rows.append(
            {
                "client_id": client_id,
                "clinic_key": clinic_key,
                "display_name": display_name,
                "secondary_name": secondary_name,
                "clinic_name": clinic_name,
                "commercial_name": commercial_name or "-",
                "client_code": (
                    knowledge_row.get("client_code")
                    or legacy_profile.get("client_code")
                )
                or client.get("external_code")
                or "-",
                "client_type": client_type_value,
                "client_type_label": CLIENT_TYPE_OPTIONS.get(client_type_value, "Sin dato"),
                "tax_id": client.get("tax_id") or "-",
                "phone": client.get("phone") or knowledge_row.get("phone") or "-",
                "email": knowledge_row.get("email") or "-",
                "billing_email": (
                    knowledge_row.get("billing_email")
                    or legacy_profile.get("billing_email")
                    or "-"
                ),
                "address": client.get("address") or knowledge_row.get("address") or "-",
                "city": client.get("city") or knowledge_row.get("locality") or "-",
                "zone": client.get("zone") or knowledge_row.get("locality") or "Sin zona",
                "courier_name": courier_data.get("name") if courier_data else "Sin mensajero",
                "assigned_courier_id": assigned_courier_id,
                "billing_type": billing_type_label,
                "client_status": "Activo" if client.get("is_active") is not False else "Inactivo",
                "registration_state": registration_state,
                "is_registered": is_registered,
                "is_new_client": is_new_client,
                "result_delivery_mode": knowledge_row.get("result_delivery_mode") or "-",
                "payment_policy": knowledge_row.get("payment_policy") or "-",
                "professional_name": professional_name_text,
                "professional_card": professional_card_text,
                "vat_regime": vat_regime_value,
                "vat_regime_label": VAT_REGIME_OPTIONS.get(vat_regime_value, "Sin dato"),
                "electronic_invoicing": electronic_invoicing_value,
                "electronic_invoicing_option": bool_to_option(electronic_invoicing_value),
                "electronic_invoicing_label": format_bool_option(electronic_invoicing_value),
                "invoicing_rut_url": (
                    knowledge_row.get("invoicing_rut_url")
                    or legacy_profile.get("invoicing_rut_url")
                    or "-"
                ),
                "registration_timestamp": registration_timestamp or "-",
                "registration_date": registration_date or "-",
                "registration_time": registration_time or "-",
                "observations": (
                    knowledge_row.get("observations")
                    or legacy_profile.get("observations")
                    or "-"
                ),
                "entered_flag": entered_flag_value,
                "entered_flag_option": bool_to_option(entered_flag_value),
                "entered_flag_label": format_bool_option(entered_flag_value),
                "profile_updated_at": (
                    knowledge_row.get("source_updated_at") or knowledge_row.get("synced_at") or "-"
                ),
                "requests_count": request_count_by_client.get(client_id, 0),
                "samples_count": sample_count_by_client.get(client_id, 0),
                "latest_request_status": latest_request_by_client.get(client_id, "-"),
                "latest_sample_status": latest_sample_by_client.get(client_id, "-"),
                "has_profile": has_knowledge,
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

    localities_assigned = len([row for row in localities_rows if row.get("is_assigned")])
    localities_total = len(localities_rows)
    localities_pending = max(localities_total - localities_assigned, 0)
    coverage_rate = round((localities_assigned / localities_total) * 100, 1) if localities_total else 0.0
    couriers_with_coverage = len(
        {
            str(row.get("assigned_courier_id") or "").strip()
            for row in localities_rows
            if str(row.get("assigned_courier_id") or "").strip()
        }
    )
    clients_in_catalog_localities = sum(locality_client_counter.values())
    clients_in_assigned_localities = sum(
        int(row.get("clients_count") or 0)
        for row in localities_rows
        if row.get("is_assigned")
    )
    clients_in_unassigned_localities = max(
        clients_in_catalog_localities - clients_in_assigned_localities,
        0,
    )
    localities_with_clients_without_coverage = len(
        [
            row
            for row in localities_rows
            if not row.get("is_assigned") and int(row.get("clients_count") or 0) > 0
        ]
    )
    couriers_without_phone = len([row for row in couriers_rows if row.get("phone_missing")])

    courier_load_leader: dict[str, Any] = {}
    if couriers_rows:
        courier_load_leader = max(
            couriers_rows,
            key=lambda row: int(row.get("clients_count_from_coverage") or 0),
        )
    busiest_courier_name = str(courier_load_leader.get("name") or "-")
    busiest_courier_clients = int(courier_load_leader.get("clients_count_from_coverage") or 0)

    motorizados_alerts: list[dict[str, Any]] = []
    if locality_coverage_demo_mode:
        motorizados_alerts.append(
            {
                "level": "warning",
                "title": "Modo demo activo",
                "detail": (
                    "Se muestran asignaciones simuladas para video/demo porque la tabla de cobertura "
                    "aun no esta disponible en esta base."
                ),
            }
        )

    if localities_pending > 0:
        motorizados_alerts.append(
            {
                "level": "warning",
                "title": "Hay localidades sin cobertura",
                "detail": (
                    f"Tienes {localities_pending} localidades sin motorizado. "
                    "Los clientes nuevos de esas zonas quedaran sin asignar."
                ),
            }
        )

    if clients_in_unassigned_localities > 0:
        motorizados_alerts.append(
            {
                "level": "danger",
                "title": "Clientes en riesgo operativo",
                "detail": (
                    f"{clients_in_unassigned_localities} clientes actuales estan en "
                    "localidades sin cobertura configurada."
                ),
            }
        )

    if couriers_without_phone > 0:
        motorizados_alerts.append(
            {
                "level": "warning",
                "title": "Datos de contacto incompletos",
                "detail": (
                    f"{couriers_without_phone} motorizados no tienen telefono valido. "
                    "Actualizalos para evitar bloqueos en operacion."
                ),
            }
        )

    if not motorizados_alerts:
        motorizados_alerts.append(
            {
                "level": "success",
                "title": "Cobertura estable",
                "detail": (
                    "No se detectan alertas criticas en motorizados. "
                    "Puedes continuar con ajustes finos de zonas."
                ),
            }
        )

    motorizados_summary = {
        "coverage_rate": coverage_rate,
        "total_localities": localities_total,
        "assigned_localities": localities_assigned,
        "pending_localities": localities_pending,
        "clients_in_catalog_localities": clients_in_catalog_localities,
        "clients_in_assigned_localities": clients_in_assigned_localities,
        "clients_in_unassigned_localities": clients_in_unassigned_localities,
        "localities_with_clients_without_coverage": localities_with_clients_without_coverage,
        "couriers_with_coverage": couriers_with_coverage,
        "couriers_without_phone": couriers_without_phone,
        "busiest_courier_name": busiest_courier_name,
        "busiest_courier_clients": busiest_courier_clients,
    }

    summary_cards = {
        "total_clients": total_clients,
        "clients_with_courier": clients_with_courier,
        "clients_without_courier": max(total_clients - clients_with_courier, 0),
        "clients_with_profile": clients_with_knowledge,
        "new_clients_indexed": clients_marked_new,
        "active_requests": len(requests_rows),
        "pending_pickup": sample_status_counter.get("pending_pickup", 0),
        "in_analysis": sample_status_counter.get("in_analysis", 0),
        "ready_results": sample_status_counter.get("ready_results", 0),
        "delivered_results": sample_status_counter.get("delivered_results", 0),
        "open_conversations": len([c for c in conversations if c.get("open_status") == "open"]),
        "catalog_tests": len(catalog),
        "total_samples": len(samples),
        "analysis_active_types": len(analysis_counter),
        "localities_total": localities_total,
        "localities_assigned": localities_assigned,
        "localities_pending": localities_pending,
        "couriers_with_coverage": couriers_with_coverage,
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

    def build_request_operation_row(
        request_row: dict[str, Any],
        *,
        force_include: bool = False,
    ) -> dict[str, Any] | None:
        request_id = str(request_row.get("id") or "").strip()
        if not request_id:
            return None

        client_id = str(request_row.get("client_id") or "").strip()
        service_area = str(request_row.get("service_area") or "").strip() or "unknown"
        intent = str(request_row.get("intent") or "").strip() or "unknown"

        samples_count_actual = sample_count_by_request.get(request_id, 0)
        sample_types_actual = sorted(sample_types_by_request.get(request_id, set()))
        manual_override = request_manual_overrides.get(request_id, {})

        if "sample_count" in manual_override:
            sample_count = int(manual_override.get("sample_count") or 0)
        else:
            sample_count = samples_count_actual

        if "sample_types" in manual_override:
            sample_types = normalize_request_sample_types_value(manual_override.get("sample_types"))
        else:
            sample_types = sample_types_actual

        for sample_type in sample_types:
            sample_type_option_set.add(sample_type)

        include_in_operations = force_include or bool(request_row.get("pickup_address")) or bool(
            samples_count_actual
        )
        if service_area == "route_scheduling" or intent == "programacion_rutas":
            include_in_operations = True

        if not include_in_operations:
            return None

        clients_payload = request_row.get("clients") if isinstance(request_row.get("clients"), dict) else {}
        clients_payload = clients_payload if isinstance(clients_payload, dict) else {}
        client_row = clients_by_id.get(client_id) or {}

        clinic_name = str(clients_payload.get("clinic_name") or client_row.get("clinic_name") or "").strip()
        if not clinic_name:
            clinic_name = "Sin cliente"

        registered_address = str(clients_payload.get("address") or client_row.get("address") or "").strip()
        pickup_address_raw = str(request_row.get("pickup_address") or "").strip()
        pickup_address = pickup_address_raw or "Sin direccion"

        address_match_state = "unknown"
        if registered_address and pickup_address_raw:
            if normalize_lookup_key(registered_address) == normalize_lookup_key(pickup_address_raw):
                address_match_state = "match"
            else:
                address_match_state = "mismatch"

        priority_db = normalize_request_priority_value(request_row.get("priority")) or "normal"
        priority = manual_override.get("priority") or priority_db
        priority = normalize_request_priority_value(priority) or "normal"

        return {
            "request_id": request_id,
            "client_id": client_id,
            "clinic_name": clinic_name,
            "service_area": service_area,
            "intent": intent,
            "priority": priority,
            "status": request_row.get("status") or "unknown",
            "pickup_address": pickup_address,
            "pickup_address_raw": pickup_address_raw,
            "registered_address": registered_address or "-",
            "address_match_state": address_match_state,
            "scheduled_pickup_date": request_row.get("scheduled_pickup_date") or "-",
            "created_at": request_row.get("created_at") or "-",
            "courier_name": (
                ((request_row.get("couriers") or {}).get("name"))
                if isinstance(request_row.get("couriers"), dict)
                else None
            )
            or "Sin asignar",
            "sample_count": sample_count,
            "sample_count_actual": samples_count_actual,
            "sample_types": sample_types,
            "sample_types_text": ", ".join(sample_types) if sample_types else "Sin muestras",
            "latest_sample_status": latest_sample_status_by_request.get(request_id, "-"),
        }

    request_operation_rows: list[dict[str, Any]] = []
    for request_row in requests_rows:
        operation_row = build_request_operation_row(request_row)
        if operation_row:
            request_operation_rows.append(operation_row)

    if not request_operation_rows:
        for request_row in requests_rows[:200]:
            operation_row = build_request_operation_row(request_row, force_include=True)
            if operation_row:
                request_operation_rows.append(operation_row)

    sample_placeholder_rows: list[dict[str, Any]] = []
    sample_placeholder_status_counter: Counter[str] = Counter()
    if not samples:
        for request_row in request_operation_rows[:120]:
            request_id = str(request_row.get("request_id") or "").strip()
            if not request_id:
                continue

            fallback_status = normalize_status_value(request_row.get("latest_sample_status"))
            if fallback_status not in SAMPLE_STATUS_LABELS:
                fallback_status = "pending_pickup"

            sample_types = normalize_request_sample_types_value(request_row.get("sample_types"))
            primary_sample_type = sample_types[0] if sample_types else "Sin tipo definido"
            priority_value = normalize_request_priority_value(request_row.get("priority")) or "normal"

            sample_placeholder_rows.append(
                {
                    "id": "",
                    "seed_token": f"request:{request_id}",
                    "request_id": request_id,
                    "client_id": str(request_row.get("client_id") or "").strip(),
                    "created_at": request_row.get("created_at") or "-",
                    "client_name": request_row.get("clinic_name") or "Sin cliente",
                    "sample_type": primary_sample_type,
                    "test_name": "Pendiente por definir",
                    "priority": REQUEST_PRIORITY_LABELS.get(priority_value, priority_value),
                    "priority_value": priority_value,
                    "status": fallback_status,
                    "courier_name": request_row.get("courier_name") or "Sin asignar",
                }
            )
            sample_placeholder_status_counter[fallback_status] += 1

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

    sample_type_options = sorted(
        sample_type_option_set,
        key=lambda value: normalize_lookup_key(value),
    )
    if not sample_type_options:
        sample_type_options = [
            "Sangre",
            "Suero",
            "Plasma",
            "Orina",
            "Materia fecal",
            "Hisopado",
            "Tejido",
        ]

    return {
        "summary": summary_cards,
        "funnel": funnel_stages,
        "top_couriers": top_couriers,
        "top_zones": top_zones,
        "top_service_areas": top_service_areas,
        "request_status": dict(request_status_counter),
        "sample_status": dict(sample_status_counter),
        "sample_placeholder_status": dict(sample_placeholder_status_counter),
        "clients": clients,
        "requests": recent_requests,
        "requests_rows": request_operation_rows,
        "conversations": conversations[:25],
        "messages": recent_messages,
        "samples": recent_samples,
        "sample_placeholder_rows": sample_placeholder_rows,
        "catalog_preview": catalog[:80],
        "clients_rows": clients_rows,
        "couriers_options": couriers_options,
        "couriers_rows": couriers_rows,
        "localities_rows": localities_rows,
        "coverage_map_points": coverage_map_points,
        "localities_geojson_url": LOCALITIES_GEOJSON_URL,
        "coverage_summary": {
            "total_localities": localities_total,
            "assigned_localities": localities_assigned,
            "pending_localities": localities_pending,
            "couriers_with_coverage": couriers_with_coverage,
            "coverage_rate": coverage_rate,
            "clients_in_catalog_localities": clients_in_catalog_localities,
            "clients_in_assigned_localities": clients_in_assigned_localities,
            "clients_in_unassigned_localities": clients_in_unassigned_localities,
            "localities_with_clients_without_coverage": localities_with_clients_without_coverage,
            "couriers_without_phone": couriers_without_phone,
        },
        "locality_coverage_demo_mode": locality_coverage_demo_mode,
        "locality_coverage_demo_reason": locality_coverage_demo_reason,
        "motorizados_summary": motorizados_summary,
        "motorizados_alerts": motorizados_alerts,
        "client_type_options": CLIENT_TYPE_OPTIONS,
        "vat_regime_options": VAT_REGIME_OPTIONS,
        "request_priority_options": [
            {"value": value, "label": label} for value, label in REQUEST_PRIORITY_OPTIONS
        ],
        "request_priority_labels": REQUEST_PRIORITY_LABELS,
        "sample_type_options": sample_type_options,
        "request_status_options": [
            {"value": value, "label": label} for value, label in REQUEST_STATUS_OPTIONS
        ],
        "request_status_labels": REQUEST_STATUS_LABELS,
        "sample_status_options": [
            {"value": value, "label": label} for value, label in SAMPLE_STATUS_OPTIONS
        ],
        "sample_status_labels": SAMPLE_STATUS_LABELS,
        "knowledge_profile_editing_enabled": knowledge_profile_editing_enabled,
        "knowledge_profile_compat_mode": knowledge_profile_compat_mode,
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

    if status in {"confirmed", "closed", "cancelled"}:
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
    _ = reply

    if requires_handoff:
        return False

    if service_area != "new_client":
        return False

    return False


def apply_accounting_conversation_guard(
    *,
    text: str,
    captured_fields: dict[str, Any],
) -> tuple[
    str,
    str,
    str,
    str,
    list[str],
    dict[str, Any],
    bool,
    str,
    str,
    str,
    str,
]:
    normalized_text = normalize_text_value(text)
    tax_id = str(captured_fields.get("accounting_tax_id") or captured_fields.get("tax_id") or "").strip()
    invoice_reference = str(captured_fields.get("accounting_invoice_reference") or "").strip()
    period_reference = str(captured_fields.get("accounting_period_reference") or "").strip()
    attempts = int(captured_fields.get("accounting_attempts", 0) or 0)

    new_data_detected = False

    detected_tax_id = extract_tax_id_candidate(text)
    if detected_tax_id:
        if not tax_id:
            tax_id = detected_tax_id
            new_data_detected = True
        elif detected_tax_id != tax_id and not invoice_reference:
            invoice_reference = detected_tax_id
            new_data_detected = True

    detected_period = extract_accounting_period_candidate(text)
    if detected_period and detected_period != period_reference:
        period_reference = detected_period
        new_data_detected = True

    detected_invoice = extract_accounting_invoice_candidate(text)
    if detected_invoice:
        candidate_invoice = detected_invoice.strip()
        if tax_id and normalize_lookup_key(candidate_invoice) == normalize_lookup_key(tax_id):
            candidate_invoice = ""
        if candidate_invoice and candidate_invoice != invoice_reference:
            if not tax_id and re.fullmatch(r"\d{5,20}", candidate_invoice):
                tax_id = candidate_invoice
            else:
                invoice_reference = candidate_invoice
            new_data_detected = True

    if not new_data_detected and re.fullmatch(r"\d{5,20}", normalized_text or ""):
        numeric_candidate = normalized_text
        if not tax_id:
            tax_id = numeric_candidate
            new_data_detected = True
        elif not invoice_reference and numeric_candidate != tax_id:
            invoice_reference = numeric_candidate
            new_data_detected = True

    if tax_id:
        captured_fields["accounting_tax_id"] = tax_id
        captured_fields["tax_id"] = tax_id
    if invoice_reference:
        captured_fields["accounting_invoice_reference"] = invoice_reference
    if period_reference:
        captured_fields["accounting_period_reference"] = period_reference

    if new_data_detected:
        attempts = 0
    elif normalized_text and not is_small_talk_only(text):
        attempts += 1

    captured_fields["accounting_attempts"] = attempts

    if tax_id and (invoice_reference or period_reference):
        period_or_invoice = invoice_reference or period_reference
        reply = (
            "Perfecto, ya tengo tus datos para contabilidad "
            f"(NIF/NIT y referencia {period_or_invoice}). "
            "Te conecto con contabilidad para revisarlo y te confirmamos en breve."
        )
        return (
            "fase_7_escalado",
            "fase_7_escalado",
            "escalated",
            "continuar_conversacion",
            [],
            captured_fields,
            True,
            "contabilidad",
            reply,
            "flow_progress",
            "",
        )

    if tax_id:
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "continuar_conversacion",
            ["numero de factura o periodo de cobro"],
            captured_fields,
            False,
            "none",
            "Perfecto, ya tengo tu NIF/NIT. Para continuar, comparteme numero de factura o periodo de cobro.",
            "flow_progress",
            "",
        )

    if invoice_reference or period_reference:
        return (
            "fase_2_recogida_datos",
            "fase_3_validacion",
            "in_progress",
            "continuar_conversacion",
            ["NIF/NIT"],
            captured_fields,
            False,
            "none",
            "Perfecto, ya tengo esa referencia. Para avanzar, comparteme tu NIF/NIT.",
            "flow_progress",
            "",
        )

    if attempts >= 2:
        return (
            "fase_7_escalado",
            "fase_7_escalado",
            "escalated",
            "continuar_conversacion",
            [],
            captured_fields,
            True,
            "contabilidad",
            "Para evitar mas demoras, te conecto con contabilidad y revisan tu caso directamente.",
            "flow_progress",
            "",
        )

    return (
        "fase_2_recogida_datos",
        "fase_3_validacion",
        "in_progress",
        "continuar_conversacion",
        ["NIF/NIT y numero de factura o periodo de cobro"],
        captured_fields,
        False,
        "none",
        "Perfecto, te ayudo con contabilidad. Para revisarlo rapido, comparteme NIF y si tienes numero de factura o periodo de cobro.",
        "flow_progress",
        "",
    )


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

    if is_route_cancellation_request(text):
        captured_fields["route_cancelled"] = "true"
        return (
            "fase_6_cierre",
            "fase_6_cierre",
            "cancelled",
            "continuar_conversacion",
            [],
            captured_fields,
        )

    if last_action == "solicitar_direccion_actualizada" and normalized_text:
        captured_fields["pickup_address"] = text.strip()
        captured_fields["pickup_address_confirmed"] = "false"
        return (
            "fase_3_validacion",
            "fase_4_confirmacion",
            "in_progress",
            "confirmar_direccion_retiro",
            ["confirmacion de direccion"],
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
            if is_client_identity_mismatch_reply(text):
                captured_fields.pop("clinic_name", None)
                captured_fields.pop("pickup_address", None)
                captured_fields.pop("pickup_address_confirmed", None)
                captured_fields.pop("tax_id", None)
                captured_fields["route_force_client_revalidation"] = "true"
                captured_fields["route_identification_attempts"] = 0
                return (
                    "fase_2_recogida_datos",
                    "fase_3_validacion",
                    "in_progress",
                    "solicitar_nif_o_nombre_fiscal",
                    ["NIF o nombre fiscal de la veterinaria"],
                    captured_fields,
                )
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


def handle_telegram_message(chat_id: int, text: str) -> None:
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
    if (
        explicit_area == "new_client"
        and session_service_area == "route_scheduling"
        and is_client_identity_mismatch_reply(text)
    ):
        explicit_area = "route_scheduling"
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
        recovery_area = detect_explicit_service_area(text)
        if not recovery_area and not used_openai_fallback:
            recovery_area = detect_semantic_service_area_hint(text)
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
            "Claro, puedo orientarte con servicios, precios aproximados y procesos del laboratorio. "
            "Cuentame que examen o necesidad tienes y te ayudo de inmediato."
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
        elif catalog_guidance_reply:
            reply = catalog_guidance_reply
            follow_up_message = ""
            next_action = "atender_otra_consulta"
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
        not is_first_turn
        and service_area == "route_scheduling"
        and not requires_handoff
        and not client_id
        and not is_meaningful_value(captured_fields.get("clinic_name"))
        and reply != INTENT_CLARIFICATION_MESSAGE
    ):
        tax_candidate = extract_tax_id_candidate(text)
        clinic_hint = extract_clinic_name_hint(text)
        tax_lookup_failed = is_truthy_flag(captured_fields.get("route_tax_lookup_failed"))
        clinic_lookup_failed = is_truthy_flag(captured_fields.get("route_clinic_lookup_failed"))
        last_failed_tax_id = normalize_tax_id(str(captured_fields.get("route_last_failed_tax_id") or ""))
        last_failed_clinic_name = normalize_lookup_key(
            str(captured_fields.get("route_last_failed_clinic_name") or "")
        )

        attempts = int(captured_fields.get("route_identification_attempts", 0) or 0) + 1
        captured_fields["route_identification_attempts"] = attempts

        if tax_candidate:
            normalized_tax_id = normalize_tax_id(tax_candidate)
            identified_client = find_registered_client_by_tax_id(tax_candidate)
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

                captured_fields.pop("route_tax_lookup_failed", None)
                captured_fields.pop("route_clinic_lookup_failed", None)
                captured_fields.pop("route_last_failed_tax_id", None)
                captured_fields.pop("route_last_failed_clinic_name", None)
                captured_fields["route_identification_attempts"] = 0
            else:
                captured_fields["route_tax_lookup_failed"] = True
                captured_fields["route_last_failed_tax_id"] = normalized_tax_id or last_failed_tax_id

                if clinic_lookup_failed:
                    phase_current = "fase_7_escalado"
                    phase_next = "fase_7_escalado"
                    status = "escalated"
                    next_action = "continuar_conversacion"
                    message_mode = "flow_progress"
                    resume_prompt = ""
                    missing_fields = []
                    requires_handoff = True
                    handoff_area = "operaciones"
                    reply = ROUTE_CLIENT_VALIDATION_HANDOFF_MESSAGE
                else:
                    phase_current = "fase_2_recogida_datos"
                    phase_next = "fase_3_validacion"
                    status = "in_progress"
                    next_action = "solicitar_nif_o_nombre_fiscal"
                    message_mode = "flow_progress"
                    resume_prompt = ""
                    missing_fields = ["nombre de la veterinaria"]
                    requires_handoff = False
                    handoff_area = "none"
                    reply = ROUTE_CLIENT_NAME_VALIDATION_MESSAGE

                    if tax_lookup_failed and normalized_tax_id == last_failed_tax_id:
                        reply = ROUTE_CLIENT_NAME_VALIDATION_MESSAGE

        elif clinic_hint and is_probable_clinic_name_input(text):
            normalized_clinic_hint = normalize_lookup_key(clinic_hint)
            identified_client = find_registered_client_by_clinic_name(clinic_hint)
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

                captured_fields.pop("route_tax_lookup_failed", None)
                captured_fields.pop("route_clinic_lookup_failed", None)
                captured_fields.pop("route_last_failed_tax_id", None)
                captured_fields.pop("route_last_failed_clinic_name", None)
                captured_fields["route_identification_attempts"] = 0
            else:
                captured_fields["route_clinic_lookup_failed"] = True
                captured_fields["route_last_failed_clinic_name"] = clinic_hint

                if tax_lookup_failed:
                    phase_current = "fase_7_escalado"
                    phase_next = "fase_7_escalado"
                    status = "escalated"
                    next_action = "continuar_conversacion"
                    message_mode = "flow_progress"
                    resume_prompt = ""
                    missing_fields = []
                    requires_handoff = True
                    handoff_area = "operaciones"
                    reply = ROUTE_CLIENT_VALIDATION_HANDOFF_MESSAGE
                else:
                    phase_current = "fase_2_recogida_datos"
                    phase_next = "fase_3_validacion"
                    status = "in_progress"
                    next_action = "solicitar_nif_o_nombre_fiscal"
                    message_mode = "flow_progress"
                    resume_prompt = ""
                    missing_fields = ["NIF/NID"]
                    requires_handoff = False
                    handoff_area = "none"
                    reply = ROUTE_CLIENT_TAX_VALIDATION_MESSAGE

                    if clinic_lookup_failed and normalized_clinic_hint == last_failed_clinic_name:
                        reply = ROUTE_CLIENT_TAX_VALIDATION_MESSAGE

        elif user_declares_not_registered(text):
            captured_fields = clear_post_registration_target(captured_fields)
            captured_fields["new_client_manual_handoff"] = "true"
            service_area = "new_client"
            intent = "alta_cliente"
            phase_current = "fase_7_escalado"
            phase_next = "fase_7_escalado"
            status = "escalated"
            next_action = "continuar_conversacion"
            message_mode = "flow_progress"
            resume_prompt = ""
            missing_fields = []
            requires_handoff = True
            handoff_area = "operaciones"
            reply = NEW_CLIENT_MANUAL_HANDOFF_MESSAGE
        else:
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
                    "Claro, puedo orientarte con servicios, precios aproximados y procesos del laboratorio. "
                    "Cuentame que examen o necesidad tienes y te ayudo de inmediato."
                )
            elif tax_lookup_failed and not clinic_lookup_failed:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["nombre de la veterinaria"]
                requires_handoff = False
                handoff_area = "none"
                reply = ROUTE_CLIENT_NAME_VALIDATION_MESSAGE
            elif clinic_lookup_failed and not tax_lookup_failed:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF/NID"]
                requires_handoff = False
                handoff_area = "none"
                reply = ROUTE_CLIENT_TAX_VALIDATION_MESSAGE
            elif tax_lookup_failed and clinic_lookup_failed:
                phase_current = "fase_7_escalado"
                phase_next = "fase_7_escalado"
                status = "escalated"
                next_action = "continuar_conversacion"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = []
                requires_handoff = True
                handoff_area = "operaciones"
                reply = ROUTE_CLIENT_VALIDATION_HANDOFF_MESSAGE
            elif attempts >= 5:
                phase_current = "fase_7_escalado"
                phase_next = "fase_7_escalado"
                status = "escalated"
                next_action = "continuar_conversacion"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = []
                requires_handoff = True
                handoff_area = "operaciones"
                reply = ROUTE_CLIENT_VALIDATION_HANDOFF_MESSAGE
            elif attempts >= 3:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF o nombre fiscal de la veterinaria"]
                requires_handoff = False
                handoff_area = "none"
                reply = (
                    "Aun no logro ubicar tu registro. Para continuar, enviame uno de estos datos:\n"
                    "- NIF/NIT (ejemplo: 900123456)\n"
                    "- Nombre de la veterinaria (ejemplo: Terra Pets)\n"
                    "Si prefieres otra gestion, escribe 2, 3, 4, 5 o 6 del menu."
                )
            elif attempts == 2:
                phase_current = "fase_2_recogida_datos"
                phase_next = "fase_3_validacion"
                status = "in_progress"
                next_action = "solicitar_nif_o_nombre_fiscal"
                message_mode = "flow_progress"
                resume_prompt = ""
                missing_fields = ["NIF o nombre fiscal de la veterinaria"]
                requires_handoff = False
                handoff_area = "none"
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
                requires_handoff = False
                handoff_area = "none"
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
            if is_no_thanks_message(text):
                phase_current = "fase_6_cierre"
                phase_next = "fase_6_cierre"
                status = "closed"
                next_action = "continuar_conversacion"
                missing_fields = []
                message_mode = "flow_progress"
                resume_prompt = ""
                reply = ROUTE_CHAT_CLOSURE_MESSAGE
            elif special_option == "pqrs":
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
                    "Claro, puedo orientarte con servicios, precios aproximados y procesos del laboratorio. "
                    "Cuentame que examen o necesidad tienes y te ayudo de inmediato."
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

        if service_area == "route_scheduling" and status not in {"closed", "cancelled"}:
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

            if is_truthy_flag(captured_fields.get("route_force_client_revalidation")):
                captured_fields.pop("route_force_client_revalidation", None)
                client = None
                client_id = None

            if next_action == "confirmar_direccion_retiro":
                clinic_label = captured_fields.get("clinic_name") or "tu veterinaria"
                address_label = captured_fields.get("pickup_address") or "la direccion registrada"
                time_window_label = str(captured_fields.get("pickup_time_window") or "").strip()
                time_window_suffix = f" en franja {time_window_label}" if time_window_label else ""
                if client_id:
                    reply = (
                        "Perfecto, ya ubique tu registro. "
                        f"Encontre la veterinaria {clinic_label} con direccion {address_label}{time_window_suffix}. "
                        "¿Confirmas que este es el cliente correcto y que la direccion de retiro es correcta?"
                    )
                else:
                    reply = (
                        "Perfecto, te ayudo con la programacion de ruta para retirar la muestra. "
                        f"¿Confirmas que el retiro es para {clinic_label} en {address_label}{time_window_suffix}?"
                    )
            elif next_action == "solicitar_direccion_actualizada":
                reply = "Perfecto, por favor comparteme la direccion actual para programar el retiro."
            elif next_action == "solicitar_nif_o_nombre_fiscal":
                reply = (
                    "Entendido, validemos el cliente correcto antes de continuar. "
                    "Comparteme tu NIF/NIT o el nombre fiscal de la veterinaria para ubicar el registro."
                )
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
                if status == "cancelled":
                    reply = ROUTE_CANCELLATION_MESSAGE
                elif status == "closed":
                    reply = ROUTE_CHAT_CLOSURE_MESSAGE
                else:
                    reply = ROUTE_ALREADY_PROGRAMMED_MESSAGE
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
                        f"¿Confirmas que el retiro es para {clinic_label} en {address_label}{time_window_suffix}?"
                    )

            resume_prompt = ""
            message_mode = "flow_progress"

    if (
        not is_first_turn
        and service_area == "accounting"
        and not requires_handoff
        and should_apply_accounting_guard(session=session, text=text, reply=reply)
    ):
        (
            phase_current,
            phase_next,
            status,
            next_action,
            missing_fields,
            captured_fields,
            requires_handoff,
            handoff_area,
            reply,
            message_mode,
            resume_prompt,
        ) = apply_accounting_conversation_guard(
            text=text,
            captured_fields=captured_fields,
        )

    if service_area == "new_client":
        captured_fields = clear_post_registration_target(captured_fields)
        captured_fields["new_client_manual_handoff"] = "true"
        intent = "alta_cliente"
        phase_current = "fase_7_escalado"
        phase_next = "fase_7_escalado"
        status = "escalated"
        requires_handoff = True
        handoff_area = "operaciones"
        next_action = "continuar_conversacion"
        missing_fields = []
        message_mode = "flow_progress"
        resume_prompt = ""
        reply = NEW_CLIENT_MANUAL_HANDOFF_MESSAGE
        follow_up_message = ""

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
        and not is_truthy_flag(captured_fields.get("new_client_manual_handoff"))
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
        elif service_area == "accounting":
            tax_id = str(captured_fields.get("accounting_tax_id") or captured_fields.get("tax_id") or "").strip()
            invoice_reference = str(captured_fields.get("accounting_invoice_reference") or "").strip()
            period_reference = str(captured_fields.get("accounting_period_reference") or "").strip()
            if tax_id and (invoice_reference or period_reference):
                reply = (
                    "Perfecto, ya tengo la informacion base. "
                    "Te conecto con contabilidad para confirmar el estado y te responden en breve."
                )
            elif tax_id:
                reply = "Perfecto, ya tengo tu NIF/NIT. Ahora comparteme numero de factura o periodo de cobro."
            else:
                reply = (
                    "Para revisarlo sin demora, comparteme por favor NIF/NIT "
                    "y numero de factura o periodo de cobro."
                )
            anti_loop_prompt = ""
        elif service_area == "unknown" and (is_catalog_inquiry(text) or is_help_inquiry(text)):
            reply = build_catalog_follow_up_reply(text)
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

    if service_area == "route_scheduling" and status == "cancelled":
        try:
            now_iso = datetime.now().isoformat()
            supabase.update_request(
                request_ref["id"],
                {
                    "status": "cancelled",
                    "updated_at": now_iso,
                },
            )
            supabase.create_request_event(
                request_id=request_ref["id"],
                event_type="route_request_cancelled",
                event_payload={
                    "source": "telegram_user_message",
                    "message_text": text,
                    "cancelled_at": now_iso,
                },
            )
        except httpx.HTTPStatusError:
            print(f"[telegram] route_cancel_update_unavailable chat_id={chat_id}")

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
        supabase.create_request_event(
            request_id=new_client_request["id"],
            event_type="human_handoff",
            event_payload={"target": "operaciones"},
        )
        telegram.send_message(
            chat_id,
            NEW_CLIENT_MANUAL_HANDOFF_MESSAGE,
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


@app.get("/solicitudes")
@login_required
def requests_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="solicitudes",
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


@app.get("/motorizados")
@login_required
def motorizados_page() -> Any:
    context = build_dashboard_context()
    return render_template(
        "dashboard.html",
        context=context,
        username=session.get("username"),
        active_tab="motorizados",
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


@app.post("/api/dashboard/client-profile")
@login_required
def dashboard_update_client_profile() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    clinic_key = normalize_lookup_key(str(payload.get("clinic_key") or ""))
    clinic_name = sanitize_profile_text(payload.get("clinic_name"), max_length=180)
    client_id = str(payload.get("client_id") or "").strip()
    field = str(payload.get("field") or "").strip()
    value = payload.get("value")

    if not clinic_key:
        return jsonify({"error": "Missing clinic_key"}), 400

    allowed_fields = {
        "client_code",
        "commercial_name",
        "client_type",
        "billing_email",
        "vat_regime",
        "electronic_invoicing",
        "invoicing_rut_url",
        "observations",
        "entered_flag",
    }
    if field not in allowed_fields:
        return jsonify({"error": "Unsupported field"}), 400

    profile_row: dict[str, Any] = {
        "clinic_key": clinic_key,
        "clinic_name": clinic_name or clinic_key,
        "source_updated_at": datetime.now().isoformat(),
    }

    legacy_profile_value: Any = ""

    if field == "client_type":
        normalized_value = normalize_client_type_value(value)
        profile_row["client_type"] = normalized_value or None
        legacy_profile_value = normalized_value
    elif field == "vat_regime":
        normalized_value = normalize_vat_regime_value(value)
        profile_row["vat_regime"] = normalized_value or None
        legacy_profile_value = normalized_value
    elif field == "electronic_invoicing":
        normalized_value = normalize_bool_option_value(value)
        profile_row["electronic_invoicing"] = normalized_value
        legacy_profile_value = bool_to_option(normalized_value)
    elif field == "entered_flag":
        normalized_value = normalize_bool_option_value(value)
        profile_row["entered_flag"] = normalized_value
        legacy_profile_value = bool_to_option(normalized_value)
    elif field == "observations":
        normalized_value = sanitize_profile_text(value, max_length=1200)
        profile_row["observations"] = normalized_value
        legacy_profile_value = normalized_value or ""
    elif field == "invoicing_rut_url":
        normalized_value = sanitize_profile_text(value, max_length=500)
        profile_row["invoicing_rut_url"] = normalized_value
        legacy_profile_value = normalized_value or ""
    elif field == "commercial_name":
        normalized_value = sanitize_profile_text(value, max_length=180)
        profile_row["commercial_name"] = normalized_value
        legacy_profile_value = normalized_value or ""
    elif field == "billing_email":
        normalized_value = sanitize_profile_text(value, max_length=180)
        profile_row["billing_email"] = normalized_value
        legacy_profile_value = normalized_value or ""
    elif field == "client_code":
        normalized_value = sanitize_profile_text(value, max_length=80)
        profile_row["client_code"] = normalized_value
        legacy_profile_value = normalized_value or ""

    try:
        supabase.upsert_client_profile(profile_row)
    except httpx.HTTPStatusError as exc:
        response_text = exc.response.text or ""
        if exc.response.status_code == 400 and "Could not find the" in response_text:
            try:
                current_rows = supabase.fetch_rows(
                    "clients_a3_knowledge",
                    {
                        "select": "clinic_key,clinic_name,sources_json",
                        "clinic_key": f"eq.{clinic_key}",
                        "limit": "1",
                    },
                )
                current_row = current_rows[0] if current_rows else None
                sources_payload = build_knowledge_sources_payload(
                    (current_row or {}).get("sources_json") if isinstance(current_row, dict) else [],
                    {field: legacy_profile_value},
                )

                if current_row:
                    supabase.update_rows(
                        "clients_a3_knowledge",
                        {"clinic_key": f"eq.{clinic_key}"},
                        {
                            "clinic_name": clinic_name or current_row.get("clinic_name") or clinic_key,
                            "sources_json": sources_payload,
                            "source_updated_at": datetime.now().isoformat(),
                        },
                    )
                else:
                    supabase.insert_rows(
                        "clients_a3_knowledge",
                        [
                            {
                                "clinic_key": clinic_key,
                                "clinic_name": clinic_name or clinic_key,
                                "is_registered": False,
                                "is_new_client": False,
                                "sources_json": sources_payload,
                                "source_excel": "dashboard_manual",
                                "source_updated_at": datetime.now().isoformat(),
                            }
                        ],
                        upsert=True,
                        on_conflict="clinic_key",
                    )
            except httpx.HTTPStatusError as fallback_exc:
                return (
                    jsonify(
                        {
                            "error": "Unable to update client profile in legacy compatibility mode",
                            "status_code": fallback_exc.response.status_code,
                        }
                    ),
                    503,
                )
        else:
            return (
                jsonify(
                    {
                        "error": "Unable to update client profile",
                        "status_code": exc.response.status_code,
                    }
                ),
                503,
            )

    if field == "client_code" and client_id:
        try:
            supabase.update_rows(
                "clients",
                {"id": f"eq.{client_id}"},
                {"external_code": profile_row.get("client_code")},
            )
        except httpx.HTTPStatusError:
            pass

    return jsonify(
        {
            "ok": True,
            "clinic_key": clinic_key,
            "field": field,
            "value": profile_row.get(field),
        }
    )


@app.post("/api/dashboard/client-assignment")
@login_required
def dashboard_update_client_assignment() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    client_id = str(payload.get("client_id") or "").strip()
    courier_id = str(payload.get("courier_id") or "").strip()

    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400

    if courier_id:
        couriers = safe_fetch(lambda: supabase.list_active_couriers(limit=2000), [])
        valid_courier_ids = {
            str(row.get("id") or "").strip()
            for row in ensure_dict_rows(couriers)
            if str(row.get("id") or "").strip()
        }
        if valid_courier_ids and courier_id not in valid_courier_ids:
            return jsonify({"error": "Invalid courier_id"}), 400

    assigned_by = f"dashboard:{session.get('username') or 'operator'}"
    try:
        supabase.upsert_client_assignment(
            client_id=client_id,
            courier_id=courier_id or None,
            assigned_by=assigned_by,
        )
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to update courier assignment",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify({"ok": True, "client_id": client_id, "courier_id": courier_id or None})


@app.post("/api/dashboard/courier-phone")
@login_required
def dashboard_update_courier_phone() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    courier_id = str(payload.get("courier_id") or "").strip()
    phone = normalize_courier_phone_value(payload.get("phone"))

    if not courier_id:
        return jsonify({"error": "Missing courier_id"}), 400
    if not phone:
        return jsonify({"error": "Invalid phone"}), 400

    couriers = safe_fetch(lambda: supabase.list_active_couriers(limit=2000), [])
    valid_courier_ids = {
        str(row.get("id") or "").strip()
        for row in ensure_dict_rows(couriers)
        if str(row.get("id") or "").strip()
    }
    if valid_courier_ids and courier_id not in valid_courier_ids:
        return jsonify({"error": "Invalid courier_id"}), 400

    try:
        supabase.update_rows(
            "couriers",
            {"id": f"eq.{courier_id}"},
            {
                "phone": phone,
                "updated_at": datetime.now().isoformat(),
            },
        )
    except httpx.HTTPStatusError as exc:
        response_text = (exc.response.text or "").lower()
        if exc.response.status_code in {400, 409} and (
            "duplicate" in response_text or "couriers_phone_key" in response_text
        ):
            return jsonify({"error": "Phone already exists for another courier"}), 409

        return (
            jsonify(
                {
                    "error": "Unable to update courier phone",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify({"ok": True, "courier_id": courier_id, "phone": phone})


@app.post("/api/dashboard/courier-locality-assignment")
@login_required
def dashboard_update_courier_locality_assignment() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    locality_code = normalize_locality_code(payload.get("locality_code"))
    courier_id = str(payload.get("courier_id") or "").strip()

    if not locality_code:
        return jsonify({"error": "Missing locality_code"}), 400
    if locality_code not in BOGOTA_LOCALITY_CODES:
        return jsonify({"error": "Unsupported locality_code"}), 400

    if courier_id:
        couriers = safe_fetch(lambda: supabase.list_active_couriers(limit=2000), [])
        valid_courier_ids = {
            str(row.get("id") or "").strip()
            for row in ensure_dict_rows(couriers)
            if str(row.get("id") or "").strip()
        }
        if valid_courier_ids and courier_id not in valid_courier_ids:
            return jsonify({"error": "Invalid courier_id"}), 400

    assigned_by = f"dashboard:{session.get('username') or 'operator'}"
    locality_name = BOGOTA_LOCALITIES_BY_CODE[locality_code]["name"]

    try:
        if courier_id:
            supabase.upsert_courier_locality_coverage(
                locality_code=locality_code,
                locality_name=locality_name,
                courier_id=courier_id,
                assigned_by=assigned_by,
            )
        else:
            supabase.delete_courier_locality_coverage(locality_code)
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to update locality coverage",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify(
        {
            "ok": True,
            "locality_code": locality_code,
            "locality_name": locality_name,
            "courier_id": courier_id or None,
        }
    )


@app.post("/api/dashboard/request-operation")
@login_required
def dashboard_update_request_operation() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        return jsonify({"error": "Missing request_id"}), 400

    has_priority = "priority" in payload
    has_sample_count = "sample_count" in payload
    has_sample_types = "sample_types" in payload

    if not (has_priority or has_sample_count or has_sample_types):
        return jsonify({"error": "Missing editable fields"}), 400

    priority = ""
    if has_priority:
        priority = normalize_request_priority_value(payload.get("priority"))
        if not priority:
            return jsonify({"error": "Invalid request priority"}), 400

    sample_count: int | None = None
    if has_sample_count:
        sample_count = normalize_request_sample_count_value(payload.get("sample_count"))
        if sample_count is None:
            return jsonify({"error": "Invalid sample_count"}), 400

    sample_types: list[str] = []
    if has_sample_types:
        sample_types = normalize_request_sample_types_value(payload.get("sample_types"))

    now_iso = datetime.now().isoformat()
    updated_by = session.get("username") or "operator"

    db_priority_value = ""
    try:
        if has_priority:
            db_priority_value = normalize_request_priority_db_value(priority)
            supabase.update_request(
                request_id,
                {
                    "priority": db_priority_value,
                    "updated_at": now_iso,
                },
            )

        event_payload: dict[str, Any] = {
            "updated_by": updated_by,
            "source": "dashboard_solicitudes",
            "updated_at": now_iso,
        }
        if has_priority:
            event_payload["priority"] = priority
            event_payload["priority_label"] = REQUEST_PRIORITY_LABELS.get(priority, priority)
            event_payload["priority_db_value"] = db_priority_value
        if has_sample_count and sample_count is not None:
            event_payload["sample_count"] = sample_count
        if has_sample_types:
            event_payload["sample_types"] = sample_types

        supabase.create_request_event(
            request_id=request_id,
            event_type="dashboard_request_manual_update",
            event_payload=event_payload,
        )
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to update request operation",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify(
        {
            "ok": True,
            "request_id": request_id,
            "priority": priority if has_priority else None,
            "priority_label": REQUEST_PRIORITY_LABELS.get(priority, priority) if has_priority else None,
            "sample_count": sample_count if has_sample_count else None,
            "sample_types": sample_types if has_sample_types else None,
        }
    )


@app.post("/api/dashboard/request-status")
@login_required
def dashboard_update_request_status() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    request_id = str(payload.get("request_id") or "").strip()
    status = normalize_status_value(payload.get("status"))

    if not request_id:
        return jsonify({"error": "Missing request_id"}), 400
    if status not in REQUEST_STATUS_LABELS:
        return jsonify({"error": "Invalid request status"}), 400

    now_iso = datetime.now().isoformat()
    updated_by = session.get("username") or "operator"

    try:
        supabase.update_request(
            request_id,
            {
                "status": status,
                "updated_at": now_iso,
            },
        )
        supabase.create_request_event(
            request_id=request_id,
            event_type="dashboard_status_update",
            event_payload={
                "status": status,
                "status_label": REQUEST_STATUS_LABELS.get(status, status),
                "updated_by": updated_by,
                "source": "dashboard_solicitudes",
                "updated_at": now_iso,
            },
        )
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to update request status",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify(
        {
            "ok": True,
            "request_id": request_id,
            "status": status,
            "status_label": REQUEST_STATUS_LABELS.get(status, status),
        }
    )


@app.post("/api/dashboard/sample-status")
@login_required
def dashboard_update_sample_status() -> Any:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid payload"}), 400

    sample_id = str(payload.get("sample_id") or "").strip()
    sample_seed = payload.get("sample_seed")
    status = normalize_status_value(payload.get("status"))

    if status not in SAMPLE_STATUS_LABELS:
        return jsonify({"error": "Invalid sample status"}), 400
    if not sample_id and not isinstance(sample_seed, dict):
        return jsonify({"error": "Missing sample_id"}), 400

    now_iso = datetime.now().isoformat()
    updated_by = session.get("username") or "operator"
    status_db = normalize_sample_status_db_value(status)

    created_from_seed = False
    persistence_mode = "event_only"
    try:
        if not sample_id and isinstance(sample_seed, dict):
            request_id_seed = normalize_uuid_value(sample_seed.get("request_id"))
            client_id_seed = normalize_uuid_value(sample_seed.get("client_id"))
            sample_type_seed = sanitize_sample_type_value(sample_seed.get("sample_type"))
            test_name_seed = sanitize_profile_text(sample_seed.get("test_name"), max_length=160)
            priority_seed = (
                normalize_request_priority_value(sample_seed.get("priority")) or "normal"
            )
            priority_db = normalize_request_priority_db_value(priority_seed)
            source_reference = sanitize_profile_text(sample_seed.get("seed_token"), max_length=120)

            create_payload: dict[str, Any] = {
                "status": status_db,
                "priority": priority_db,
                "source_system": "dashboard_manual",
                "source_reference": source_reference or "dashboard_seed",
                "updated_at": now_iso,
            }
            if request_id_seed:
                create_payload["request_id"] = request_id_seed
            if client_id_seed:
                create_payload["client_id"] = client_id_seed
            if sample_type_seed:
                create_payload["sample_type"] = sample_type_seed
            if test_name_seed:
                create_payload["test_name"] = test_name_seed

            created_rows = supabase.insert_rows("lab_samples", [create_payload])
            created_row = created_rows[0] if created_rows else {}
            sample_id = str((created_row or {}).get("id") or "").strip()
            if not sample_id:
                return jsonify({"error": "Unable to create sample"}), 503

            created_from_seed = True
            if status in SAMPLE_STATUS_DB_OPTIONS:
                persistence_mode = "created_lab_sample_and_event"
            else:
                persistence_mode = "created_lab_sample_fallback_and_event"
        elif status in SAMPLE_STATUS_DB_OPTIONS:
            supabase.update_rows(
                "lab_samples",
                {"id": f"eq.{sample_id}"},
                {
                    "status": status,
                    "updated_at": now_iso,
                },
            )
            persistence_mode = "lab_samples_and_event"

        supabase.insert_rows(
            "lab_sample_events",
            [
                {
                    "sample_id": sample_id,
                    "event_type": "dashboard_status_update",
                    "event_payload": {
                        "status": status,
                        "status_label": SAMPLE_STATUS_LABELS.get(status, status),
                        "updated_by": updated_by,
                        "source": "dashboard_muestras",
                        "persistence_mode": persistence_mode,
                        "created_from_seed": created_from_seed,
                        "status_db": status_db,
                        "updated_at": now_iso,
                    },
                }
            ],
        )
    except httpx.HTTPStatusError as exc:
        return (
            jsonify(
                {
                    "error": "Unable to update sample status",
                    "status_code": exc.response.status_code,
                }
            ),
            503,
        )

    return jsonify(
        {
            "ok": True,
            "sample_id": sample_id,
            "status": status,
            "status_label": SAMPLE_STATUS_LABELS.get(status, status),
            "persistence_mode": persistence_mode,
            "created_from_seed": created_from_seed,
        }
    )


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
    resolved_locality = resolve_bogota_locality(locality) or resolve_bogota_locality(address)
    locality_code = str((resolved_locality or {}).get("code") or "").strip()
    locality_name = str((resolved_locality or {}).get("name") or locality or "").strip()
    phone = extract_form_value(payload, ("N Celular", "Celular o Telefono", "N Celular de comunicacion"))
    email = extract_form_value(payload, ("Email", "Correo o WhatsApp", "Correo"))
    tax_id = extract_form_value(payload, ("Rut", "Informacion en RUT", "NIT", "Nif"))
    client_code = extract_form_value(payload, ("Codigo", "Codigo cliente", "C"))
    commercial_name = extract_form_value(payload, ("Nombre Comercial", "Nombre comercial"))
    client_type = normalize_client_type_value(
        extract_form_value(payload, ("Tipo", "Tipo de cliente"))
    )
    billing_email = extract_form_value(
        payload,
        (
            "Correo (En el cual te llegaran las facturas)",
            "Correo facturacion",
            "Correo para facturacion",
        ),
    )
    vat_regime = normalize_vat_regime_value(
        extract_form_value(payload, ("Tipo de regimen IVA", "Regimen IVA", "Regimen"))
    )
    electronic_invoicing = normalize_bool_option_value(
        extract_form_value(payload, ("Facturacion Electronica", "Facturacion electronica"))
    )
    invoicing_rut_url = extract_form_value(
        payload,
        (
            "Si deseas factura electronica adjuntar el Rut",
            "Informacion en RUT",
            "Rut para facturacion",
        ),
    )
    entered_flag = normalize_bool_option_value(
        extract_form_value(payload, ("Ingresado", "Registrado"))
    )
    registration_timestamp = extract_form_value(
        payload,
        ("Marca temporal", "Timestamp", "Fecha y hora de registro"),
    )
    registration_date = extract_form_value(payload, ("Fecha", "Fecha registro"))
    registration_time = extract_form_value(payload, ("Hora", "Hora registro"))
    observations = extract_form_value(payload, ("Observaciones", "Informacion suministrada"))

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

    legacy_profile_payload = {
        "client_code": client_code or "",
        "commercial_name": commercial_name or "",
        "client_type": client_type or "",
        "billing_email": billing_email or "",
        "vat_regime": vat_regime or "",
        "electronic_invoicing": bool_to_option(electronic_invoicing),
        "invoicing_rut_url": invoicing_rut_url or "",
        "registration_timestamp": registration_timestamp or now_iso,
        "registration_date": registration_date or now_iso[:10],
        "registration_time": registration_time or now_iso[11:16],
        "observations": observations or "",
        "entered_flag": bool_to_option(entered_flag),
    }

    knowledge_row = {
        "clinic_key": clinic_key,
        "clinic_name": clinic_name,
        "is_registered": True,
        "is_new_client": True,
        "address": address or None,
        "locality": locality_name or None,
        "phone": phone or None,
        "email": email or None,
        "payment_policy": None,
        "result_delivery_mode": result_delivery_mode or None,
        "client_code": client_code or None,
        "commercial_name": commercial_name or None,
        "client_type": client_type or None,
        "billing_email": billing_email or None,
        "vat_regime": vat_regime or None,
        "electronic_invoicing": electronic_invoicing,
        "invoicing_rut_url": invoicing_rut_url or None,
        "registration_timestamp": registration_timestamp or now_iso,
        "registration_date": registration_date or now_iso[:10],
        "registration_time": registration_time or now_iso[11:16],
        "observations": observations or None,
        "entered_flag": entered_flag,
        "sources_json": ["google_form_webhook"],
        "source_excel": "google_form_webhook",
        "source_updated_at": now_iso,
    }

    knowledge_row_legacy = {
        "clinic_key": clinic_key,
        "clinic_name": clinic_name,
        "is_registered": True,
        "is_new_client": True,
        "address": address or None,
        "locality": locality_name or None,
        "phone": phone or None,
        "email": email or None,
        "payment_policy": None,
        "result_delivery_mode": result_delivery_mode or None,
        "sources_json": build_knowledge_sources_payload(
            ["google_form_webhook"],
            legacy_profile_payload,
        ),
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

    registered_client_id = ""
    auto_assignment = {
        "attempted": False,
        "assigned": False,
        "locality_code": locality_code or None,
        "locality_name": locality_name or None,
        "courier_id": None,
        "courier_name": None,
        "reason": "pending",
    }

    try:
        try:
            supabase.insert_rows(
                "clients_a3_knowledge",
                [knowledge_row],
                upsert=True,
                on_conflict="clinic_key",
            )
        except httpx.HTTPStatusError as knowledge_exc:
            response_text = knowledge_exc.response.text or ""
            if knowledge_exc.response.status_code == 400 and "Could not find the" in response_text:
                supabase.insert_rows(
                    "clients_a3_knowledge",
                    [knowledge_row_legacy],
                    upsert=True,
                    on_conflict="clinic_key",
                )
            else:
                raise
        if professional_row["professional_key"]:
            supabase.insert_rows(
                "clients_a3_professionals",
                [professional_row],
                upsert=True,
                on_conflict="clinic_key,professional_key,source_sheet",
            )

        if address:
            base_client_payload = {
                "external_code": client_code or None,
                "clinic_name": clinic_name,
                "tax_id": tax_id or None,
                "phone": phone or None,
                "address": address,
                "city": locality_name or None,
                "zone": locality_name or None,
                "billing_type": "cash",
                "is_active": True,
            }
            if phone:
                created_clients = supabase.insert_rows(
                    "clients",
                    [base_client_payload],
                    upsert=True,
                    on_conflict="phone",
                )
            else:
                created_clients = supabase.insert_rows("clients", [base_client_payload])

            first_client = created_clients[0] if created_clients else {}
            registered_client_id = str((first_client or {}).get("id") or "").strip()
            if not registered_client_id and phone:
                matched_client = supabase.get_client_by_phone(phone)
                registered_client_id = str((matched_client or {}).get("id") or "").strip()

            if locality_code and registered_client_id:
                auto_assignment["attempted"] = True
                try:
                    locality_assignment = supabase.get_courier_for_locality_code(locality_code)
                except httpx.HTTPStatusError:
                    auto_assignment["reason"] = "coverage_table_not_ready"
                else:
                    assigned_courier_id = str(
                        (locality_assignment or {}).get("courier_id") or ""
                    ).strip()
                    courier_payload = (
                        (locality_assignment or {}).get("couriers")
                        if isinstance((locality_assignment or {}).get("couriers"), dict)
                        else {}
                    )
                    if assigned_courier_id:
                        try:
                            supabase.upsert_client_assignment(
                                client_id=registered_client_id,
                                courier_id=assigned_courier_id,
                                assigned_by="auto_locality_new_client",
                            )
                        except httpx.HTTPStatusError:
                            auto_assignment["reason"] = "assignment_write_failed"
                        else:
                            auto_assignment.update(
                                {
                                    "assigned": True,
                                    "courier_id": assigned_courier_id,
                                    "courier_name": courier_payload.get("name"),
                                    "reason": "assigned_by_locality_coverage",
                                }
                            )
                    else:
                        auto_assignment["reason"] = "locality_without_courier_coverage"
            elif not locality_code:
                auto_assignment["reason"] = "locality_not_recognized"
            elif not registered_client_id:
                auto_assignment["reason"] = "client_id_not_available"
        else:
            auto_assignment["reason"] = "missing_address"
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
            "locality_code": locality_code or None,
            "locality_name": locality_name or None,
            "auto_assignment": auto_assignment,
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
