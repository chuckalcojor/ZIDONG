import json
import unittest

from app.services.openai_service import OpenAIService


class OpenAIServiceTests(unittest.TestCase):
    def test_safe_json_loads_handles_wrapped_text(self) -> None:
        service = OpenAIService(api_key="test", model="gpt-5-mini")
        parsed = service._safe_json_loads("respuesta: {\"intent\": \"programacion_rutas\"}")
        self.assertEqual(parsed["intent"], "programacion_rutas")

    def test_generate_turn_uses_fallback_model_on_parse_failure(self) -> None:
        calls: list[str] = []

        service = OpenAIService(
            api_key="test",
            model="gpt-5-mini",
            fallback_model="gpt-4.1-mini",
            enable_fallback=True,
        )

        def fake_post(payload: dict, *, timeout: int):
            model = payload["model"]
            calls.append(model)
            if model == "gpt-5-mini":
                return {"output_text": "texto no json"}
            return {"output_text": "{\"intent\":\"programacion_rutas\",\"service_area\":\"route_scheduling\"}"}

        service._post_responses = fake_post  # type: ignore[method-assign]

        result = service.generate_turn(
            system_prompt="system",
            user_message="necesito una ruta",
            state={},
        )

        self.assertEqual(calls, ["gpt-5-mini", "gpt-4.1-mini"])
        self.assertEqual(result.get("service_area"), "route_scheduling")

    def test_classify_service_area_returns_unknown_when_all_models_fail(self) -> None:
        service = OpenAIService(
            api_key="test",
            model="gpt-5-mini",
            fallback_model="gpt-4.1-mini",
            enable_fallback=True,
        )

        def fake_post(payload: dict, *, timeout: int):
            return {"output_text": "sin json"}

        service._post_responses = fake_post  # type: ignore[method-assign]

        result = service.classify_service_area(user_message="ayuda")
        self.assertEqual(result, "unknown")

    def test_generate_turn_schema_supports_pickup_time_window_alias(self) -> None:
        service = OpenAIService(
            api_key="test",
            model="gpt-5-mini",
            fallback_model="gpt-4.1-mini",
            enable_fallback=False,
        )
        captured_payload: dict = {}

        def fake_post(payload: dict, *, timeout: int):
            _ = timeout
            captured_payload.update(payload)
            return {
                "output_text": json.dumps(
                    {
                        "reply": "Perfecto, te ayudo con eso.",
                        "intent": "programacion_rutas",
                        "service_area": "route_scheduling",
                        "phase_current": "fase_2_recogida_datos",
                        "phase_next": "fase_3_validacion",
                        "status": "in_progress",
                        "requires_handoff": False,
                        "handoff_area": "none",
                        "missing_fields": [],
                        "captured_fields": {
                            "phone": None,
                            "clinic_name": None,
                            "pet_name": None,
                            "sample_reference": None,
                            "order_reference": None,
                            "pickup_address": None,
                            "pickup_time_window": "jornada de la tarde",
                            "priority": "normal",
                        },
                        "next_action": "continuar_conversacion",
                        "message_mode": "flow_progress",
                        "resume_prompt": "",
                        "confidence": 0.9,
                    }
                )
            }

        service._post_responses = fake_post  # type: ignore[method-assign]

        result = service.generate_turn(
            system_prompt="system",
            user_message="ruta en la tarde",
            state={},
        )

        self.assertEqual(result.get("service_area"), "route_scheduling")
        captured_schema = (
            captured_payload["text"]["format"]["schema"]["properties"]["captured_fields"]
        )
        captured_props = captured_schema["properties"]
        self.assertIn("pickup_time_window", captured_props)
        self.assertIn("time_window", captured_props)
        self.assertTrue(captured_schema.get("additionalProperties"))
        self.assertNotIn("required", captured_schema)


if __name__ == "__main__":
    unittest.main()
