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


if __name__ == "__main__":
    unittest.main()
