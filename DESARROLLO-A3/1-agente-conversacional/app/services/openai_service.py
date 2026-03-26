from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAIService:
    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def generate_turn(
        self,
        *,
        system_prompt: str,
        user_message: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
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
            "max_output_tokens": 700,
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
                                "properties": {
                                    "phone": {"type": ["string", "null"]},
                                    "clinic_name": {"type": ["string", "null"]},
                                    "pet_name": {"type": ["string", "null"]},
                                    "sample_reference": {"type": ["string", "null"]},
                                    "order_reference": {"type": ["string", "null"]},
                                    "pickup_address": {"type": ["string", "null"]},
                                    "time_window": {"type": ["string", "null"]},
                                    "priority": {
                                        "type": ["string", "null"],
                                        "enum": ["normal", "urgent", None],
                                    },
                                },
                                "required": [
                                    "phone",
                                    "clinic_name",
                                    "pet_name",
                                    "sample_reference",
                                    "order_reference",
                                    "pickup_address",
                                    "time_window",
                                    "priority",
                                ],
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

        with httpx.Client(timeout=45) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        text = (body.get("output_text") or "").strip()
        if text:
            return json.loads(text)

        for output_item in body.get("output", []):
            for content_item in output_item.get("content", []):
                json_payload = content_item.get("json")
                if isinstance(json_payload, dict):
                    return json_payload
                content_text = (content_item.get("text") or "").strip()
                if content_text:
                    return json.loads(content_text)

        raise ValueError("Empty OpenAI response")
