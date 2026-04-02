from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app import main
from tests.test_conversation_flow import FakeSupabase, FakeTelegram, make_session


AREAS = ("route_scheduling", "results", "accounting", "new_client")


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


def run_single_turn_eval(
    selected_areas: list[str],
    progress_every: int,
) -> tuple[list[EvalResult], dict[str, Counter[str]]]:
    real_openai = main.openai_service
    results: list[EvalResult] = []
    confusion: dict[str, Counter[str]] = {area: Counter() for area in selected_areas}

    chat_id = 900000
    for area in selected_areas:
        prompts = build_50_prompts(area)
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
            main.openai_service = real_openai

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
) -> list[dict[str, object]]:
    real_openai = main.openai_service
    outcomes: list[dict[str, object]] = []
    followup = {
        "route_scheduling": "mi nif es 900123456",
        "results": "mi numero de orden es 12345",
        "accounting": "mi nif es 900123456",
        "new_client": "quiero registrarme ahora",
    }

    chat_id = 990000
    for area in selected_areas:
        prompts = build_50_prompts(area)[:samples_per_area]
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
            main.openai_service = real_openai

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

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": getattr(main.openai_service, "model", "unknown"),
        "single_turn_total": len(single_turn),
        "single_turn_accuracy": round(total_ok / max(1, len(single_turn)) * 100, 2),
        "single_turn_avg_latency_ms": round(statistics.mean(total_latency), 2),
        "single_turn_p95_latency_ms": round(percentile(total_latency, 0.95), 2),
        "multiturn_total": len(multiturn),
        "multiturn_logic_accuracy": round(multiturn_ok / max(1, len(multiturn)) * 100, 2),
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
    single_turn, confusion = run_single_turn_eval(selected_areas, progress_every=progress_every)
    multiturn = run_multiturn_logic_eval(
        selected_areas,
        samples_per_area=args.multiturn_samples,
        progress_every=progress_every,
    )
    summary = build_report(single_turn, confusion, multiturn, selected_areas)

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
