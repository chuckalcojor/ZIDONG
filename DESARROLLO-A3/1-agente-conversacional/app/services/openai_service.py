from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx


class OpenAIService:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        fallback_model: str | None = None,
        enable_fallback: bool = True,
        max_retries: int = 1,
    ) -> None:
        self.model = model
        self.fallback_model = (fallback_model or "").strip() or None
        self.enable_fallback = enable_fallback
        self.max_retries = max(0, max_retries)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def quick_health_check(self, *, timeout: int = 4) -> bool:
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": self.headers["Authorization"]},
                    params={"limit": 1},
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def _safe_json_loads(self, raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("Empty OpenAI response text")

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("Could not parse JSON object from OpenAI text")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI payload is not a JSON object")
        return parsed

    def _post_responses(self, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(
                        "https://api.openai.com/v1/responses",
                        headers=self.headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status_code = exc.response.status_code
                is_retryable = status_code == 429 or status_code >= 500
                if not is_retryable or attempt >= self.max_retries:
                    raise
                time.sleep(0.6 * (attempt + 1))
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(0.4 * (attempt + 1))

        if last_exc:
            raise last_exc
        raise RuntimeError("OpenAI request failed without explicit exception")

    def _extract_output_json(self, body: dict[str, Any]) -> dict[str, Any]:
        output_parsed = body.get("output_parsed")
        if isinstance(output_parsed, dict):
            return output_parsed

        text = (body.get("output_text") or "").strip()
        if text:
            return self._safe_json_loads(text)

        for output_item in body.get("output", []):
            if not isinstance(output_item, dict):
                continue
            for content_item in output_item.get("content", []):
                if not isinstance(content_item, dict):
                    continue
                json_payload = content_item.get("json")
                if isinstance(json_payload, dict):
                    return json_payload
                content_text = (content_item.get("text") or "").strip()
                if content_text:
                    return self._safe_json_loads(content_text)

        raise ValueError("Empty OpenAI response")

    def _candidate_models(self) -> list[str]:
        models = [self.model]
        if self.enable_fallback:
            if self.fallback_model and self.fallback_model != self.model:
                models.append(self.fallback_model)
            elif self.model != "gpt-4.1-mini":
                models.append("gpt-4.1-mini")

        deduped_models: list[str] = []
        seen_models: set[str] = set()
        for model_name in models:
            if model_name in seen_models:
                continue
            deduped_models.append(model_name)
            seen_models.add(model_name)

        return deduped_models

    def generate_turn(
        self,
        *,
        system_prompt: str,
        user_message: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        captured_fields_properties = {
            "phone": {"type": ["string", "null"]},
            "clinic_name": {"type": ["string", "null"]},
            "pet_name": {"type": ["string", "null"]},
            "sample_reference": {"type": ["string", "null"]},
            "order_reference": {"type": ["string", "null"]},
            "pickup_address": {"type": ["string", "null"]},
            "time_window": {"type": ["string", "null"]},
            "pickup_time_window": {"type": ["string", "null"]},
            "priority": {
                "type": ["string", "null"],
                "enum": ["normal", "urgent", None],
            },
        }

        payload_template = {
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": system_prompt,
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "instruction": "Respond only with strict JSON.",
                                    "conversation_state": state,
                                    "incoming_message": user_message,
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ],
                },
            ],
            "max_output_tokens": 1200,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "a3_turn_output",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "reply": {"type": "string"},
                            "intent": {
                                "type": "string",
                                "enum": [
                                    "programacion_rutas",
                                    "contabilidad",
                                    "resultados",
                                    "alta_cliente",
                                    "no_clasificado",
                                ],
                            },
                            "service_area": {
                                "type": "string",
                                "enum": [
                                    "route_scheduling",
                                    "accounting",
                                    "results",
                                    "new_client",
                                    "unknown",
                                ],
                            },
                            "phase_current": {
                                "type": "string",
                                "enum": [
                                    "fase_0_bienvenida",
                                    "fase_1_clasificacion",
                                    "fase_2_recogida_datos",
                                    "fase_3_validacion",
                                    "fase_4_confirmacion",
                                    "fase_5_ejecucion",
                                    "fase_6_cierre",
                                    "fase_7_escalado",
                                ],
                            },
                            "phase_next": {
                                "type": "string",
                                "enum": [
                                    "fase_0_bienvenida",
                                    "fase_1_clasificacion",
                                    "fase_2_recogida_datos",
                                    "fase_3_validacion",
                                    "fase_4_confirmacion",
                                    "fase_5_ejecucion",
                                    "fase_6_cierre",
                                    "fase_7_escalado",
                                ],
                            },
                            "status": {
                                "type": "string",
                                "enum": [
                                    "in_progress",
                                    "confirmed",
                                    "closed",
                                    "escalated",
                                ],
                            },
                            "requires_handoff": {"type": "boolean"},
                            "handoff_area": {
                                "type": "string",
                                "enum": ["none", "contabilidad", "tecnico", "operaciones"],
                            },
                            "missing_fields": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "captured_fields": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": captured_fields_properties,
                                "required": list(captured_fields_properties.keys()),
                            },
                            "next_action": {"type": "string"},
                            "message_mode": {
                                "type": "string",
                                "enum": [
                                    "flow_progress",
                                    "side_question",
                                    "intent_switch",
                                    "small_talk",
                                ],
                            },
                            "resume_prompt": {"type": "string"},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": [
                            "reply",
                            "intent",
                            "service_area",
                            "phase_current",
                            "phase_next",
                            "status",
                            "requires_handoff",
                            "handoff_area",
                            "missing_fields",
                            "captured_fields",
                            "next_action",
                            "message_mode",
                            "resume_prompt",
                            "confidence",
                        ],
                    },
                }
            },
        }
        last_exc: Exception | None = None
        for model_name in self._candidate_models():
            payload = {**payload_template, "model": model_name}
            try:
                body = self._post_responses(payload, timeout=20)
                parsed = self._extract_output_json(body)
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError("Turn payload is not a dict")
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                last_exc = exc
                continue

        if last_exc:
            raise last_exc
        raise ValueError("Empty OpenAI response")

    def classify_service_area(self, *, user_message: str) -> str:
        payload_template = {
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Clasifica el mensaje de un cliente veterinario en una sola area de servicio. "
                                "Responde solo JSON con la clave service_area."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "instruction": "Responde solo con JSON valido.",
                                    "service_areas": [
                                        "route_scheduling",
                                        "results",
                                        "accounting",
                                        "new_client",
                                        "unknown",
                                    ],
                                    "message": user_message,
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ],
                },
            ],
            "max_output_tokens": 80,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "a3_service_area_classifier",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "service_area": {
                                "type": "string",
                                "enum": [
                                    "route_scheduling",
                                    "results",
                                    "accounting",
                                    "new_client",
                                    "unknown",
                                ],
                            }
                        },
                        "required": ["service_area"],
                    },
                }
            },
        }

        for model_name in self._candidate_models():
            payload = {**payload_template, "model": model_name}
            try:
                body = self._post_responses(payload, timeout=10)
                parsed = self._extract_output_json(body)
                return str(parsed.get("service_area") or "unknown")
            except (httpx.HTTPError, ValueError, json.JSONDecodeError):
                continue

        return "unknown"
