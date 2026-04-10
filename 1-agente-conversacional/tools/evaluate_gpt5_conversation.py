from __future__ import annotations

import argparse
import json
import random
import sys
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import main
from tests.test_conversation_flow import FakeSupabase, FakeTelegram, make_session


AREAS = ("route_scheduling", "results", "accounting", "new_client")

STRESS_SAMPLES_PER_AREA = 80


PROMPT_BASES: dict[str, dict[str, list[str]]] = {
    "route_scheduling": {
        "explicit": [
            "quiero programar una ruta",
            "necesito recoger una muestra",
            "quiero enviar una muestra al laboratorio",
            "necesito retiro de muestra",
            "quiero coordinar mensajero para muestras",
            "mandar examen a analizar",
            "recoleccion de muestra hoy",
            "programar domicilio para retiro",
            "enviar pruebas al laboratorio",
            "agendar recogida de muestras",
        ],
        "semantic": [
            "tengo tubos listos y necesito que pasen por ellos",
            "quiero coordinar la logistica de toma y envio",
            "me ayudas a mover unas analiticas hoy",
            "hay material biologico pendiente de despacho",
            "necesito que me gestionen el retiro en clinica",
            "quiero activar la ruta para procesar paneles",
            "tengo examenes para remitir y no se por donde empezar",
            "como hago para que pasen por unas muestras urgentes",
            "necesito apoyo de motorizado para laboratorio",
            "quiero coordinar la recogida domiciliaria de analiticas",
        ],
    },
    "results": {
        "explicit": [
            "quiero consultar resultados",
            "necesito el informe de una muestra",
            "estado de resultados por favor",
            "quiero saber si ya salio el reporte",
            "consultar resultado de examen",
            "me compartes el diagnostico",
            "resultado de laboratorio pendiente",
            "ver estado de un informe",
            "quiero revisar un reporte",
            "estado de un resultado veterinario",
        ],
        "semantic": [
            "me ayudas a validar si ya quedo lista la lectura",
            "necesito saber en que va una orden del paciente",
            "quiero confirmar si ya cerraron el estudio",
            "me puedes indicar si ya esta publicado el analisis",
            "aun no me llega la entrega del caso",
            "quiero seguimiento de un caso de laboratorio",
            "me preocupa el tiempo de salida del informe",
            "me ayudas con el avance del procesamiento",
            "quiero confirmar si ya hay dictamen",
            "necesito trazabilidad de un caso reportado",
        ],
    },
    "accounting": {
        "explicit": [
            "necesito contabilidad",
            "quiero revisar una factura",
            "consulta de cartera",
            "estado de cuenta por favor",
            "tengo dudas de pago",
            "quiero ver saldo pendiente",
            "consulta de cobro",
            "necesito soporte de facturacion",
            "revisar deuda con laboratorio",
            "pregunta sobre abonos",
        ],
        "semantic": [
            "me ayudas a cuadrar lo financiero de este mes",
            "quiero aclarar montos que no me coinciden",
            "tengo una diferencia en valores cobrados",
            "necesito conciliar pagos pendientes",
            "quiero validar el corte de mi cuenta",
            "me puedes apoyar con temas de cobro",
            "tengo inquietud por un cargo en mi cuenta",
            "quiero confirmar que recibieron mi abono",
            "necesito soporte para cierre contable",
            "me puedes detallar los pendientes de pago",
        ],
    },
    "new_client": {
        "explicit": [
            "quiero registrarme como cliente",
            "soy cliente nuevo",
            "primera vez con ustedes",
            "necesito alta de cliente",
            "quiero crear mi registro",
            "quiero vincular mi veterinaria",
            "aun no estoy registrado",
            "quiero afiliar mi clinica",
            "como me registro",
            "me ayudan con el formulario de alta",
        ],
        "semantic": [
            "quiero empezar a trabajar con ustedes",
            "nunca he usado el servicio y quiero iniciar",
            "me ayudas a quedar en la base de clientes",
            "quiero habilitar mi cuenta de veterinaria",
            "necesito onboarding para laboratorio",
            "quiero dar de alta mi negocio",
            "necesito ingresar por primera vez",
            "quiero abrir historial con ustedes",
            "me interesa vincularme como nuevo aliado",
            "quiero formalizar mi ingreso al servicio",
        ],
    },
}


PREFIXES = [
    "",
    "porfa",
    "me ayudas",
    "necesito ayuda",
    "hola",
    "buen dia",
    "urgente",
    "cuando puedas",
    "equipo",
    "consulta",
]

SUFFIXES = [
    "",
    "por favor",
    "gracias",
    "cuando puedas",
    "es urgente",
    "hoy mismo",
    "si es posible",
    "quedo atento",
    "gracias de antemano",
    "me confirmas",
]


@dataclass
class EvalResult:
    area: str
    prompt: str
    group: str
    predicted_area: str
    intent: str
    next_action: str
    latency_ms: float
    response_len: int
    response_score: int
    ok: bool
    error: str


class OfflineOpenAIStub:
    model = "offline-eval-stub"

    def classify_service_area(self, user_message: str) -> str:
        _ = user_message
        return "unknown"

    def generate_turn(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "intent": "no_clasificado",
            "service_area": "unknown",
            "phase_current": "fase_1_clasificacion",
            "phase_next": "fase_2_recogida_datos",
            "next_action": "atender_otra_consulta",
            "status": "in_progress",
            "reply": "Entiendo, te ayudo con gusto.",
            "missing_fields": [],
            "captured_fields": {},
            "message_mode": "flow_progress",
        }


@dataclass
class QualityScenario:
    name: str
    prompt: str
    expected_area: str | None
    expected_tokens: tuple[str, ...]
    forbidden_tokens: tuple[str, ...]
    requires_clarification: bool = False


QUALITY_SCENARIOS: tuple[QualityScenario, ...] = (
    QualityScenario(
        name="catalog_orina_general",
        prompt="que analisis de orina manejan y como es la toma?",
        expected_area="unknown",
        expected_tokens=("orina", "toma", "servicios"),
        forbidden_tokens=("factura", "cartera"),
    ),
    QualityScenario(
        name="catalog_coombs_price",
        prompt="soy veterinario, precio de coombs y tiempos",
        expected_area="unknown",
        expected_tokens=("coombs", "valor", "tiempo"),
        forbidden_tokens=("factura", "pqrs"),
    ),
    QualityScenario(
        name="route_operational",
        prompt="quiero enviar una muestra al laboratorio y programar retiro",
        expected_area="route_scheduling",
        expected_tokens=("nif", "veterinaria"),
        forbidden_tokens=("factura",),
    ),
    QualityScenario(
        name="results_status",
        prompt="hola, me ayudas con el estado del resultado de una muestra",
        expected_area="results",
        expected_tokens=("resultado", "numero"),
        forbidden_tokens=("factura",),
    ),
    QualityScenario(
        name="accounting_balance",
        prompt="necesito revisar saldo pendiente y factura",
        expected_area="accounting",
        expected_tokens=("cartera", "pago", "factura"),
        forbidden_tokens=("muestra",),
    ),
    QualityScenario(
        name="new_client_onboarding",
        prompt="es primera vez, quiero registrarme como cliente",
        expected_area="new_client",
        expected_tokens=("registro", "formulario"),
        forbidden_tokens=("resultado",),
    ),
    QualityScenario(
        name="mixed_route_and_catalog",
        prompt="quiero programar recogida y de paso precio de creatinina",
        expected_area="route_scheduling",
        expected_tokens=("nif", "veterinaria"),
        forbidden_tokens=("pqrs",),
    ),
    QualityScenario(
        name="ambiguous_clarification",
        prompt="hola, necesito ayuda urgente",
        expected_area=None,
        expected_tokens=(),
        forbidden_tokens=("factura", "cartera", "programada"),
        requires_clarification=True,
    ),
)


def seed_eval_catalog(fake_supabase: FakeSupabase) -> None:
    fake_supabase.catalog_tests = [
        {
            "test_code": "1109",
            "test_name": "Prueba de Coombs Tubos Tapa Morada y Tapa Roja",
            "category": "D.C.",
            "subcategory": "3 horas a partir de ingreso al laboratorio",
            "sample_type": "sangre",
            "price_cop": 28000,
            "turnaround_hours": 3,
            "is_active": True,
        },
        {
            "test_code": "1309",
            "test_name": "Creatinina Tubo Rojo o Amarillo",
            "category": "D.C.",
            "subcategory": "3 horas a partir de ingreso al laboratorio",
            "sample_type": "sangre",
            "price_cop": 12000,
            "turnaround_hours": 3,
            "is_active": True,
        },
        {
            "test_code": "1701",
            "test_name": "Coprologico Materia Fecal",
            "category": "D.C.",
            "subcategory": "3 horas a partir de ingreso al laboratorio",
            "sample_type": "materia fecal",
            "price_cop": 12000,
            "turnaround_hours": 3,
            "is_active": True,
        },
        {
            "test_code": "2102",
            "test_name": "Urocultivo y Antibiograma Orina Fresca y Esteril",
            "category": "D.C.",
            "subcategory": "Dependiendo del Cultivo",
            "sample_type": "orina",
            "price_cop": 80000,
            "turnaround_hours": None,
            "is_active": True,
        },
    ]


def score_quality_dimensions(
    scenario: QualityScenario,
    *,
    predicted_area: str,
    response: str,
) -> dict[str, int]:
    text = (response or "").strip().lower()

    comprehension = 0
    if scenario.expected_area is None:
        comprehension = 100
    elif predicted_area == scenario.expected_area:
        comprehension = 100
    elif scenario.expected_area == "unknown" and any(token in text for token in ("servicios", "analisis", "examen")):
        comprehension = 100

    coherence = 100 if text else 0
    if any(token in text for token in scenario.forbidden_tokens):
        coherence = max(0, coherence - 60)
    if scenario.expected_tokens and not any(token in text for token in scenario.expected_tokens):
        coherence = max(0, coherence - 30)

    naturality = 60 if len(text) >= 30 else 20
    if any(token in text for token in ("perfecto", "claro", "te ayudo", "genial", "entiendo")):
        naturality += 25
    if text.count("?") > 2:
        naturality -= 10
    naturality = max(0, min(100, naturality))

    utility = 0
    if any(token in text for token in ("valor", "tiempo", "muestra", "nif", "formulario", "numero")):
        utility += 70
    if scenario.expected_tokens and any(token in text for token in scenario.expected_tokens):
        utility += 30
    utility = min(100, utility)

    safety = 100
    if any(token in text for token in scenario.forbidden_tokens):
        safety -= 70
    if scenario.requires_clarification and "?" not in text:
        safety -= 30
    safety = max(0, safety)

    return {
        "comprehension": comprehension,
        "coherence": coherence,
        "naturality": naturality,
        "utility": utility,
        "safety": safety,
    }


def run_quality_suite(progress_every: int, use_offline_stub: bool) -> tuple[list[dict[str, Any]], dict[str, float]]:
    real_openai = main.openai_service
    eval_openai = OfflineOpenAIStub() if use_offline_stub else real_openai
    outcomes: list[dict[str, Any]] = []
    chat_id = 970000

    for idx, scenario in enumerate(QUALITY_SCENARIOS, start=1):
        fake_supabase = FakeSupabase()
        fake_telegram = FakeTelegram()
        fake_supabase.sessions[str(chat_id)] = make_session(chat_id)
        seed_eval_catalog(fake_supabase)

        main.supabase = fake_supabase
        main.telegram = fake_telegram
        main.openai_service = eval_openai

        started = time.perf_counter()
        error = ""
        predicted_area = "error"
        response = ""
        try:
            main.handle_telegram_message(chat_id, scenario.prompt)
            session = fake_supabase.sessions.get(str(chat_id), {})
            predicted_area = str(session.get("service_area") or "unknown")
            response = fake_telegram.messages[-1][1] if fake_telegram.messages else ""
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        latency_ms = (time.perf_counter() - started) * 1000
        dimensions = score_quality_dimensions(
            scenario,
            predicted_area=predicted_area,
            response=response,
        )

        outcomes.append(
            {
                "name": scenario.name,
                "prompt": scenario.prompt,
                "predicted_area": predicted_area,
                "latency_ms": round(latency_ms, 2),
                "dimensions": dimensions,
                "response": response,
                "error": error,
            }
        )
        chat_id += 1

        if idx % progress_every == 0 or idx == len(QUALITY_SCENARIOS):
            print(f"[quality] progress={idx}/{len(QUALITY_SCENARIOS)}", flush=True)

    if not outcomes:
        return outcomes, {k: 0.0 for k in ("comprehension", "coherence", "naturality", "utility", "safety")}

    metric_names = ("comprehension", "coherence", "naturality", "utility", "safety")
    aggregate = {
        metric: round(
            statistics.mean(float(outcome["dimensions"][metric]) for outcome in outcomes),
            2,
        )
        for metric in metric_names
    }
    return outcomes, aggregate


def build_50_prompts(area: str) -> list[tuple[str, str]]:
    prompts: list[tuple[str, str]] = []
    groups = ("explicit", "semantic")
    for i in range(50):
        group = groups[(i // 25) % 2]
        base_list = PROMPT_BASES[area][group]
        base = base_list[i % len(base_list)]
        prefix = PREFIXES[(i * 3) % len(PREFIXES)]
        suffix = SUFFIXES[(i * 5) % len(SUFFIXES)]
        parts = [part.strip() for part in (prefix, base, suffix) if part.strip()]
        prompt = " ".join(parts)
        prompts.append((group, prompt))
    return prompts


def build_stress_prompts(area: str, target: int = STRESS_SAMPLES_PER_AREA) -> list[tuple[str, str]]:
    casual_openers = [
        "hola",
        "buen dia",
        "buenas",
        "me ayudas",
        "porfa",
        "cuando puedas",
        "oye",
        "consulta",
        "parce",
        "bro",
        "equipo",
        "urgente",
    ]
    closers = [
        "por favor",
        "gracias",
        "si es posible",
        "es urgente",
        "quedo atento",
        "me confirmas",
        "cuando tengas un minuto",
        "", 
    ]
    noise_fragments = [
        "",
        "estoy en consulta",
        "andamos full hoy",
        "te escribo rapido",
        "perdon la ortografia",
        "ando con afan",
        "desde el celu",
    ]

    professional_by_area: dict[str, list[str]] = {
        "route_scheduling": [
            "necesito coordinar retiro de muestras biologicas",
            "programemos recoleccion para paneles de hematologia y bioquimica",
            "tengo remision lista para mensajero",
            "quiero activar ruta para despachar analiticas",
            "necesito logistica de retiro en clinica",
            "tengo tubos y laminas para procesamiento",
            "quiero remitir examenes hoy mismo",
            "coordinamos motorizado para recogida",
            "me ayudas a agendar la ruta",
            "necesito despachar muestras de pacientes",
        ],
        "results": [
            "necesito trazabilidad de una orden",
            "quiero validar estado del informe",
            "me compartes el dictamen de laboratorio",
            "requiero seguimiento del procesamiento",
            "el resultado ya fue liberado?",
            "consulta de avance del estudio",
            "quiero confirmar fecha de salida del reporte",
            "tengo pendiente un informe diagnostico",
            "estado de muestra remitida",
            "ayuda con lectura final del caso",
        ],
        "accounting": [
            "necesito conciliacion de pagos",
            "quiero validar cartera pendiente",
            "hay diferencia en montos facturados",
            "me apoyas con estado de cuenta",
            "consulta de abonos y saldo",
            "requiero soporte de facturacion",
            "quiero revisar un cargo en cuenta",
            "validemos cierre financiero del mes",
            "detalle de pendientes contables",
            "soporte para auditoria de cobro",
        ],
        "new_client": [
            "quiero vincular la clinica al laboratorio",
            "necesito alta de cliente veterinario",
            "es primera vez, quiero iniciar convenio",
            "como formalizo el registro de la veterinaria",
            "quiero onboarding para usar el servicio",
            "aun no estoy en la base de clientes",
            "me ayudas con formulario de alta",
            "quiero habilitar mi cuenta como aliado",
            "deseo registrarme para enviar muestras",
            "quiero crear el perfil de mi clinica",
        ],
    }
    casual_by_area: dict[str, list[str]] = {
        "route_scheduling": [
            "quiero que pasen por unas muestras",
            "me recogen unos examenes hoy?",
            "necesito mandar unas pruebas",
            "como hago para enviar unas muestras",
            "quiero pedir motorizado",
            "tengo cosas para laboratorio",
            "ayudame a sacar una ruta",
            "quiero agendar retiro",
            "pasan por la vet?",
            "me ayudas con recogida",
        ],
        "results": [
            "ya salieron los resultados?",
            "como va el examen de mi paciente",
            "me pasas el reporte",
            "ya esta listo el resultado",
            "sabes si ya quedo ese informe",
            "vengo por estado de una muestra",
            "me ayudas con un resultado",
            "todavia no me llega el informe",
            "quiero ver si ya cerraron eso",
            "tengo duda de una orden",
        ],
        "accounting": [
            "tengo duda con una factura",
            "cuanto debo de cartera",
            "me sale un cobro raro",
            "me ayudas con pagos pendientes",
            "quiero revisar saldo",
            "necesito soporte de pago",
            "tengo un tema financiero",
            "quiero cuadrar lo de la cuenta",
            "pueden revisar mi deuda",
            "consulta de cobro porfa",
        ],
        "new_client": [
            "soy nuevo con ustedes",
            "me quiero registrar",
            "no estoy inscrito",
            "quiero empezar con ustedes",
            "como me doy de alta",
            "quiero entrar como cliente",
            "primera vez aca",
            "quiero abrir cuenta",
            "no aparezco en la base",
            "me pasan el formulario de registro",
        ],
    }

    typo_overrides = {
        "muestras": ["muestrs", "muestrass", "muetras"],
        "resultados": ["resutlados", "resultadso"],
        "factura": ["factrua", "facturaa"],
        "registrar": ["registar", "registrr"],
        "orina": ["ornia", "urina"],
    }

    mixed_cross_area = {
        "route_scheduling": [
            "quiero programar recogida y de paso precio de coombs",
            "me ayudas con ruta, luego miro resultados",
            "agendamos retiro y despues revisamos cartera",
        ],
        "results": [
            "quiero resultados y tambien saber precio de creatinina",
            "reviso informe y luego te pregunto por ruta",
            "estado de orden y despues factura",
        ],
        "accounting": [
            "necesito factura y aparte precio de urocultivo",
            "cuenta pendiente y luego veo resultados",
            "quiero cartera y despues registrarme",
        ],
        "new_client": [
            "quiero registrarme y de paso saber como enviar muestras",
            "soy nuevo, tambien me interesan precios",
            "primera vez y necesito saber tiempos de resultados",
        ],
    }

    random.seed(42 + hash(area) % 97)
    prompts: list[tuple[str, str]] = []
    bases = (
        [("professional", text) for text in professional_by_area[area]]
        + [("casual", text) for text in casual_by_area[area]]
        + [("mixed", text) for text in mixed_cross_area[area]]
    )

    idx = 0
    while len(prompts) < target:
        label, base = bases[idx % len(bases)]
        opener = casual_openers[(idx * 3) % len(casual_openers)]
        closer = closers[(idx * 5) % len(closers)]
        noise = noise_fragments[(idx * 7) % len(noise_fragments)]
        text = " ".join(part for part in (opener, base, noise, closer) if part).strip()

        for correct, variants in typo_overrides.items():
            if correct in text and idx % 9 == 0:
                text = text.replace(correct, variants[(idx // 9) % len(variants)])
                break

        prompts.append((label, text))
        idx += 1

    return prompts[:target]


def response_quality_score(area: str, response: str) -> int:
    text = (response or "").strip().lower()
    if not text:
        return 0

    score = 40
    if len(text) >= 35:
        score += 20
    if len(text) >= 80:
        score += 10

    expected_tokens = {
        "route_scheduling": ("ruta", "retiro", "recoger", "nif", "veterinaria"),
        "results": ("resultado", "informe", "orden", "referencia"),
        "accounting": ("factura", "cartera", "pago", "cuenta", "saldo"),
        "new_client": ("registro", "cliente", "formulario", "alta", "vincular"),
    }
    if any(token in text for token in expected_tokens[area]):
        score += 20

    if any(token in text for token in ("por favor", "te ayudo", "perfecto", "claro")):
        score += 10

    contradiction_tokens = {
        "route_scheduling": ("factura", "cartera"),
        "results": ("programar ruta", "mensajero"),
        "accounting": ("resultado", "muestra"),
        "new_client": ("resultado", "cartera"),
    }
    if any(token in text for token in contradiction_tokens[area]):
        score -= 15

    return max(0, min(100, score))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    return ordered[idx]


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def run_single_turn_eval(
    selected_areas: list[str],
    progress_every: int,
    samples_per_area: int,
    use_offline_stub: bool,
) -> tuple[list[EvalResult], dict[str, Counter[str]]]:
    real_openai = main.openai_service
    eval_openai = OfflineOpenAIStub() if use_offline_stub else real_openai
    results: list[EvalResult] = []
    confusion: dict[str, Counter[str]] = {area: Counter() for area in selected_areas}

    chat_id = 900000
    for area in selected_areas:
        prompts = build_stress_prompts(area, target=samples_per_area)
        print(f"[single-turn] area={area} total={len(prompts)}", flush=True)
        for idx, (group, prompt) in enumerate(prompts, start=1):
            fake_supabase = FakeSupabase()
            fake_telegram = FakeTelegram()
            fake_supabase.sessions[str(chat_id)] = make_session(chat_id)
            fake_supabase.clients.append(
                {
                    "id": "client-terra",
                    "clinic_name": "Terra Pets",
                    "phone": "+573001234567",
                    "tax_id": "900123456",
                    "address": "CL 2 87F 31",
                }
            )
            fake_supabase.clients_by_tax["900123456"] = fake_supabase.clients[0]

            main.supabase = fake_supabase
            main.telegram = fake_telegram
            main.openai_service = eval_openai

            started = time.perf_counter()
            error = ""
            predicted_area = "error"
            intent = "error"
            next_action = "error"
            response = ""

            try:
                main.handle_telegram_message(chat_id, prompt)
                session = fake_supabase.sessions.get(str(chat_id), {})
                predicted_area = str(session.get("service_area") or "unknown")
                intent = str(session.get("intent_current") or "unknown")
                next_action = str(session.get("next_action") or "unknown")
                response = fake_telegram.messages[-1][1] if fake_telegram.messages else ""
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

            latency_ms = (time.perf_counter() - started) * 1000
            score = response_quality_score(area, response)
            ok = predicted_area == area and not error

            results.append(
                EvalResult(
                    area=area,
                    prompt=prompt,
                    group=group,
                    predicted_area=predicted_area,
                    intent=intent,
                    next_action=next_action,
                    latency_ms=latency_ms,
                    response_len=len(response),
                    response_score=score,
                    ok=ok,
                    error=error,
                )
            )
            confusion[area][predicted_area] += 1
            chat_id += 1
            if idx % progress_every == 0 or idx == len(prompts):
                ok_count = sum(1 for row in results if row.area == area and row.ok)
                print(
                    f"[single-turn] area={area} progress={idx}/{len(prompts)} ok={ok_count}",
                    flush=True,
                )

    return results, confusion


def run_multiturn_logic_eval(
    selected_areas: list[str],
    samples_per_area: int = 10,
    progress_every: int = 5,
    use_offline_stub: bool = False,
) -> list[dict[str, object]]:
    real_openai = main.openai_service
    eval_openai = OfflineOpenAIStub() if use_offline_stub else real_openai
    outcomes: list[dict[str, object]] = []
    followup = {
        "route_scheduling": "mi nif es 900123456",
        "results": "mi numero de orden es 12345",
        "accounting": "mi nif es 900123456",
        "new_client": "quiero registrarme ahora",
    }

    chat_id = 990000
    for area in selected_areas:
        prompts = build_stress_prompts(area, target=max(samples_per_area, 12))[:samples_per_area]
        print(f"[multi-turn] area={area} total={len(prompts)}", flush=True)
        for idx, (group, prompt) in enumerate(prompts, start=1):
            fake_supabase = FakeSupabase()
            fake_telegram = FakeTelegram()
            fake_supabase.sessions[str(chat_id)] = make_session(chat_id)
            fake_supabase.clients.append(
                {
                    "id": "client-terra",
                    "clinic_name": "Terra Pets",
                    "phone": "+573001234567",
                    "tax_id": "900123456",
                    "address": "CL 2 87F 31",
                }
            )
            fake_supabase.clients_by_tax["900123456"] = fake_supabase.clients[0]

            main.supabase = fake_supabase
            main.telegram = fake_telegram
            main.openai_service = eval_openai

            started = time.perf_counter()
            error = ""
            area_turn_1 = "unknown"
            area_turn_2 = "unknown"

            try:
                main.handle_telegram_message(chat_id, prompt)
                area_turn_1 = str(fake_supabase.sessions[str(chat_id)].get("service_area") or "unknown")
                main.handle_telegram_message(chat_id, followup[area])
                area_turn_2 = str(fake_supabase.sessions[str(chat_id)].get("service_area") or "unknown")
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

            latency_ms = (time.perf_counter() - started) * 1000
            logic_ok = area_turn_1 == area and area_turn_2 == area and not error
            outcomes.append(
                {
                    "area": area,
                    "group": group,
                    "prompt": prompt,
                    "area_turn_1": area_turn_1,
                    "area_turn_2": area_turn_2,
                    "latency_ms": round(latency_ms, 2),
                    "logic_ok": logic_ok,
                    "error": error,
                }
            )
            chat_id += 1
            if idx % progress_every == 0 or idx == len(prompts):
                ok_count = sum(1 for row in outcomes if row["area"] == area and bool(row["logic_ok"]))
                print(
                    f"[multi-turn] area={area} progress={idx}/{len(prompts)} logic_ok={ok_count}",
                    flush=True,
                )

    return outcomes


def build_report(
    single_turn: list[EvalResult],
    confusion: dict[str, Counter[str]],
    multiturn: list[dict[str, object]],
    quality_outcomes: list[dict[str, Any]],
    quality_aggregate: dict[str, float],
    selected_areas: list[str],
) -> dict[str, object]:
    by_area: dict[str, dict[str, object]] = {}
    total_ok = 0

    for area in selected_areas:
        area_rows = [row for row in single_turn if row.area == area]
        ok_count = sum(1 for row in area_rows if row.ok)
        total_ok += ok_count
        explicit_rows = [row for row in area_rows if row.group == "explicit"]
        semantic_rows = [row for row in area_rows if row.group == "semantic"]
        by_area[area] = {
            "samples": len(area_rows),
            "accuracy": round(ok_count / max(1, len(area_rows)) * 100, 2),
            "accuracy_explicit": round(
                sum(1 for row in explicit_rows if row.ok) / max(1, len(explicit_rows)) * 100,
                2,
            ),
            "accuracy_semantic": round(
                sum(1 for row in semantic_rows if row.ok) / max(1, len(semantic_rows)) * 100,
                2,
            ),
            "avg_latency_ms": round(statistics.mean(row.latency_ms for row in area_rows), 2),
            "p95_latency_ms": round(percentile([row.latency_ms for row in area_rows], 0.95), 2),
            "avg_response_score": round(statistics.mean(row.response_score for row in area_rows), 2),
            "avg_response_len": round(statistics.mean(row.response_len for row in area_rows), 2),
            "confusion": dict(confusion[area]),
        }

    total_latency = [row.latency_ms for row in single_turn]
    multiturn_ok = sum(1 for row in multiturn if bool(row["logic_ok"]))

    mismatch_rows = [
        {
            "area": row.area,
            "group": row.group,
            "predicted_area": row.predicted_area,
            "prompt": row.prompt,
            "response_score": row.response_score,
        }
        for row in single_turn
        if not row.ok
    ]
    mismatch_rows = sorted(mismatch_rows, key=lambda item: item["response_score"])[:25]

    dim_threshold = 70
    quality_lowlights: dict[str, list[dict[str, object]]] = {
        "comprehension": [],
        "coherence": [],
        "naturality": [],
        "utility": [],
        "safety": [],
    }
    for outcome in quality_outcomes:
        dims = outcome.get("dimensions", {})
        if not isinstance(dims, dict):
            continue
        for dim in quality_lowlights:
            score = to_int(dims.get(dim, 0))
            if score < dim_threshold:
                quality_lowlights[dim].append(
                    {
                        "name": outcome.get("name"),
                        "score": score,
                        "prompt": outcome.get("prompt"),
                        "predicted_area": outcome.get("predicted_area"),
                    }
                )
    for dim in quality_lowlights:
        quality_lowlights[dim] = sorted(quality_lowlights[dim], key=lambda item: to_int(item.get("score")))[:10]

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": getattr(main.openai_service, "model", "unknown"),
        "single_turn_total": len(single_turn),
        "single_turn_accuracy": round(total_ok / max(1, len(single_turn)) * 100, 2),
        "single_turn_avg_latency_ms": round(statistics.mean(total_latency), 2),
        "single_turn_p95_latency_ms": round(percentile(total_latency, 0.95), 2),
        "multiturn_total": len(multiturn),
        "multiturn_logic_accuracy": round(multiturn_ok / max(1, len(multiturn)) * 100, 2),
        "quality_suite_total": len(quality_outcomes),
        "quality_dimensions": quality_aggregate,
        "quality_suite_cases": quality_outcomes,
        "quality_lowlights": quality_lowlights,
        "single_turn_mismatches_top": mismatch_rows,
        "by_area": by_area,
    }


def to_markdown(summary: dict[str, object]) -> str:
    lines = []
    lines.append("# Reporte avanzado - evaluacion conversacional GPT-5")
    lines.append("")
    lines.append(f"- Fecha: {summary['timestamp']}")
    lines.append(f"- Modelo evaluado: {summary['model']}")
    lines.append(f"- Muestras single-turn: {summary['single_turn_total']}")
    lines.append(f"- Exactitud single-turn: {summary['single_turn_accuracy']}%")
    lines.append(f"- Latencia media single-turn: {summary['single_turn_avg_latency_ms']} ms")
    lines.append(f"- P95 latencia single-turn: {summary['single_turn_p95_latency_ms']} ms")
    lines.append(f"- Muestras multi-turn: {summary['multiturn_total']}")
    lines.append(f"- Exactitud logica multi-turn: {summary['multiturn_logic_accuracy']}%")
    lines.append(f"- Casos quality-suite: {summary['quality_suite_total']}")
    lines.append("")

    quality_dimensions = summary.get("quality_dimensions", {})
    if isinstance(quality_dimensions, dict) and quality_dimensions:
        lines.append("## Quality Dimensions")
        lines.append("")
        lines.append(f"- Comprension: {quality_dimensions.get('comprehension', 0)}")
        lines.append(f"- Coherencia: {quality_dimensions.get('coherence', 0)}")
        lines.append(f"- Naturalidad: {quality_dimensions.get('naturality', 0)}")
        lines.append(f"- Utilidad: {quality_dimensions.get('utility', 0)}")
        lines.append(f"- Seguridad: {quality_dimensions.get('safety', 0)}")
        lines.append("")
        lowlights = summary.get("quality_lowlights", {})
        if isinstance(lowlights, dict):
            lines.append("## Top Gaps By Dimension")
            lines.append("")
            for dim in ("comprehension", "coherence", "naturality", "utility", "safety"):
                cases = lowlights.get(dim, [])
                if not isinstance(cases, list) or not cases:
                    continue
                lines.append(f"### {dim}")
                for case in cases[:5]:
                    if not isinstance(case, dict):
                        continue
                    lines.append(
                        f"- [{case.get('score', 0)}] {case.get('name', 'case')} -> area={case.get('predicted_area', 'unknown')} | prompt={case.get('prompt', '')}"
                    )
                lines.append("")

    lines.append("## Resultados por opcion")
    lines.append("")

    by_area = summary["by_area"]
    assert isinstance(by_area, dict)
    for area in AREAS:
        if area not in by_area:
            continue
        area_data = by_area[area]
        assert isinstance(area_data, dict)
        lines.append(f"### {area}")
        lines.append(f"- Samples: {area_data['samples']}")
        lines.append(f"- Accuracy: {area_data['accuracy']}%")
        lines.append(f"- Accuracy explicit: {area_data['accuracy_explicit']}%")
        lines.append(f"- Accuracy semantic: {area_data['accuracy_semantic']}%")
        lines.append(f"- Latencia media: {area_data['avg_latency_ms']} ms")
        lines.append(f"- P95 latencia: {area_data['p95_latency_ms']} ms")
        lines.append(f"- Calidad de respuesta (0-100): {area_data['avg_response_score']}")
        lines.append(f"- Longitud media respuesta: {area_data['avg_response_len']} chars")
        lines.append(f"- Matriz de confusion: {json.dumps(area_data['confusion'], ensure_ascii=True)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evalua flujo conversacional con prompts sinteticos")
    parser.add_argument(
        "--areas",
        default="all",
        help="Lista separada por coma de areas (route_scheduling,results,accounting,new_client) o all",
    )
    parser.add_argument(
        "--single-turn-samples",
        type=int,
        default=STRESS_SAMPLES_PER_AREA,
        help="Cantidad de prompts single-turn por area",
    )
    parser.add_argument(
        "--multiturn-samples",
        type=int,
        default=10,
        help="Cantidad de casos multi-turn por area",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=5,
        help="Imprime avance cada N casos",
    )
    parser.add_argument(
        "--skip-quality-suite",
        action="store_true",
        help="Omite ejecucion del bloque de quality dimensions",
    )
    parser.add_argument(
        "--offline-stub",
        action="store_true",
        help="Usa stub local de OpenAI para benchmark rapido y deterministico",
    )
    return parser.parse_args()


def resolve_areas(raw_areas: str) -> list[str]:
    if raw_areas.strip().lower() == "all":
        return list(AREAS)
    selected = [item.strip() for item in raw_areas.split(",") if item.strip()]
    invalid = [item for item in selected if item not in AREAS]
    if invalid:
        raise ValueError(f"Areas invalidas: {', '.join(invalid)}")
    if not selected:
        raise ValueError("Debe seleccionar al menos un area")
    return selected


def main_cli() -> None:
    args = parse_args()
    selected_areas = resolve_areas(args.areas)
    progress_every = max(1, int(args.progress_every))
    print(
        json.dumps(
            {
                "event": "start",
                "areas": selected_areas,
                "multiturn_samples": args.multiturn_samples,
                "progress_every": progress_every,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    single_turn_samples = max(1, int(args.single_turn_samples))
    single_turn, confusion = run_single_turn_eval(
        selected_areas,
        progress_every=progress_every,
        samples_per_area=single_turn_samples,
        use_offline_stub=bool(args.offline_stub),
    )
    multiturn = run_multiturn_logic_eval(
        selected_areas,
        samples_per_area=args.multiturn_samples,
        progress_every=progress_every,
        use_offline_stub=bool(args.offline_stub),
    )
    quality_outcomes: list[dict[str, Any]] = []
    quality_aggregate: dict[str, float] = {}
    if not args.skip_quality_suite:
        quality_outcomes, quality_aggregate = run_quality_suite(
            progress_every=progress_every,
            use_offline_stub=bool(args.offline_stub),
        )
    summary = build_report(
        single_turn,
        confusion,
        multiturn,
        quality_outcomes,
        quality_aggregate,
        selected_areas,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(".tmp") / "evaluations"
    out_dir.mkdir(parents=True, exist_ok=True)

    area_suffix = "-".join(selected_areas)
    json_path = out_dir / f"gpt5_eval_{area_suffix}_{timestamp}.json"
    md_path = out_dir / f"gpt5_eval_{area_suffix}_{timestamp}.md"

    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(summary), encoding="utf-8")

    print(json.dumps({"summary": summary, "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=True))


if __name__ == "__main__":
    main_cli()
