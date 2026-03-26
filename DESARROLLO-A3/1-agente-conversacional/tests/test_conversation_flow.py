import unittest

from app import main


class FakeSupabase:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.message_events: list[dict] = []
        self.request_counter = 0
        self.clients_by_tax: dict[str, dict] = {}
        self.clients: list[dict] = []

    def get_client_by_phone(self, phone: str):
        for client in self.clients:
            if client.get("phone") == phone:
                return client
        return None

    def get_client_by_tax_id(self, tax_id: str):
        return self.clients_by_tax.get(tax_id)

    def search_clients_by_clinic_name(self, clinic_name: str, limit: int = 5):
        needle = (clinic_name or "").strip().lower()
        matches = [
            client
            for client in self.clients
            if needle and needle in (client.get("clinic_name") or "").lower()
        ]
        return matches[:limit]

    def get_telegram_session(self, chat_id: str):
        return self.sessions.get(chat_id)

    def upsert_telegram_session(self, payload: dict):
        self.sessions[payload["external_chat_id"]] = payload
        return payload

    def list_telegram_message_events(self, external_chat_id: str, limit: int = 10):
        rows = [
            row for row in self.message_events if row.get("external_chat_id") == external_chat_id
        ]
        return rows[-limit:]

    def create_telegram_message_event(self, payload: dict):
        self.message_events.append(payload)
        return payload

    def create_request(self, payload: dict):
        self.request_counter += 1
        return {"id": f"req-{self.request_counter}", **payload}

    def create_request_event(self, request_id: str, event_type: str, event_payload: dict):
        return {
            "request_id": request_id,
            "event_type": event_type,
            "event_payload": event_payload,
        }

    def create_conversation_stage_event(self, payload: dict):
        return payload


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class FakeOpenAI:
    def __init__(self, resolver):
        self.resolver = resolver

    def generate_turn(self, system_prompt: str, user_message: str, state: dict):
        return self.resolver(user_message, state)


def make_turn(**overrides):
    base = {
        "intent": "programacion_rutas",
        "service_area": "route_scheduling",
        "phase_current": "fase_2_recogida_datos",
        "phase_next": "fase_3_validacion",
        "status": "in_progress",
        "missing_fields": ["direccion de recogida"],
        "captured_fields": {},
        "requires_handoff": False,
        "handoff_area": "none",
        "next_action": "continuar_conversacion",
        "message_mode": "flow_progress",
        "resume_prompt": "",
        "confidence": 0.9,
        "reply": "Perfecto, te ayudo con eso.",
    }
    base.update(overrides)
    return base


def make_session(chat_id: int, **overrides):
    base = {
        "channel": "telegram",
        "external_chat_id": str(chat_id),
        "client_id": None,
        "request_id": None,
        "intent_current": "no_clasificado",
        "service_area": "unknown",
        "phase_current": "fase_1_clasificacion",
        "phase_next": "fase_2_recogida_datos",
        "status": "in_progress",
        "missing_fields": [],
        "captured_fields": {},
        "ai_confidence": None,
        "requires_handoff": False,
        "handoff_area": "none",
        "last_user_message": "",
        "last_bot_message": "",
        "next_action": "continuar_conversacion",
    }
    base.update(overrides)
    return base


class ConversationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_supabase = main.supabase
        self.original_telegram = main.telegram
        self.original_openai = main.openai_service

        self.fake_supabase = FakeSupabase()
        self.fake_telegram = FakeTelegram()
        main.supabase = self.fake_supabase
        main.telegram = self.fake_telegram

    def tearDown(self) -> None:
        main.supabase = self.original_supabase
        main.telegram = self.original_telegram
        main.openai_service = self.original_openai

    def test_first_turn_sends_welcome(self) -> None:
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())
        main.handle_telegram_message(101, "hola")
        self.assertTrue(self.fake_telegram.messages)
        self.assertEqual(self.fake_telegram.messages[-1][1], main.INITIAL_GREETING_MESSAGE)

    def test_route_requires_nif_or_clinic_when_client_unknown(self) -> None:
        self.fake_supabase.sessions["102"] = make_session(102)
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())
        main.handle_telegram_message(102, "quiero programar un retiro")
        self.assertEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)

    def test_analyze_sample_phrase_goes_to_identification_gate(self) -> None:
        self.fake_supabase.sessions["111"] = make_session(111)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                reply="Entiendo.",
            )
        )
        main.handle_telegram_message(111, "quiero mandar a analizar una muestra")
        self.assertEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)
        stored = self.fake_supabase.sessions["111"]
        self.assertEqual(stored["service_area"], "route_scheduling")

    def test_variant_sample_submission_phrase_goes_to_identification_gate(self) -> None:
        self.fake_supabase.sessions["113"] = make_session(113)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                reply="Entiendo.",
            )
        )
        main.handle_telegram_message(113, "necesito mandar una muestras a analizar")
        self.assertEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)
        stored = self.fake_supabase.sessions["113"]
        self.assertEqual(stored["service_area"], "route_scheduling")

    def test_route_progresses_when_tax_id_matches(self) -> None:
        self.fake_supabase.sessions["103"] = make_session(103, next_action="solicitar_nif_o_nombre_fiscal")
        self.fake_supabase.clients_by_tax["900123456"] = {
            "id": "client-1",
            "clinic_name": "Vet Norte",
            "address": "Cra 10 # 12-34",
            "phone": "+573001112233",
            "tax_id": "900123456",
        }
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())
        main.handle_telegram_message(103, "Mi NIF es 900123456")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn("programacion de ruta", sent)
        self.assertNotEqual(sent, main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)

    def test_route_without_registration_derives_to_form(self) -> None:
        self.fake_supabase.sessions["104"] = make_session(104, next_action="solicitar_nif_o_nombre_fiscal")
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())
        main.handle_telegram_message(104, "no estoy registrado")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn(main.NEW_CLIENT_REGISTRATION_FORM_URL, sent)

    def test_anti_loop_adds_resume_prompt_for_generic_reply(self) -> None:
        self.fake_supabase.sessions["105"] = make_session(
            105,
            intent_current="contabilidad",
            service_area="accounting",
            last_bot_message="Gracias. Te ayudo con eso.",
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="contabilidad",
                service_area="accounting",
                missing_fields=["telefono"],
                reply="Gracias. Te ayudo con eso.",
            )
        )
        main.handle_telegram_message(105, "sigo pendiente")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn("numero de contacto", sent.lower())

    def test_anti_loop_shortens_repeated_registration_message(self) -> None:
        self.fake_supabase.sessions["106"] = make_session(
            106,
            intent_current="alta_cliente",
            service_area="new_client",
            last_bot_message=main.NEW_CLIENT_REGISTRATION_MESSAGE,
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                missing_fields=[],
                reply=main.NEW_CLIENT_REGISTRATION_MESSAGE,
            )
        )
        main.handle_telegram_message(106, "ok")
        sent = self.fake_telegram.messages[-1][1]
        self.assertNotEqual(sent, main.NEW_CLIENT_REGISTRATION_MESSAGE)
        self.assertIn("me avisas", sent.lower())

    def test_registration_completed_message_moves_to_classification(self) -> None:
        self.fake_supabase.sessions["114"] = make_session(
            114,
            intent_current="alta_cliente",
            service_area="new_client",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="compartir_formulario_registro_cliente",
            last_bot_message=main.NEW_CLIENT_REGISTRATION_MESSAGE,
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=[],
                reply=main.NEW_CLIENT_REGISTRATION_MESSAGE,
            )
        )

        main.handle_telegram_message(114, "ya me registre")

        sent = self.fake_telegram.messages[-1][1]
        self.assertEqual(sent, main.NEW_CLIENT_POST_REGISTRATION_MESSAGE)
        self.assertNotIn(main.NEW_CLIENT_REGISTRATION_FORM_URL, sent)
        self.assertNotIn("me avisas", sent.lower())

        stored = self.fake_supabase.sessions["114"]
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "solicitar_clasificacion")

    def test_registration_completed_variant_keeps_progress_without_repeating_form(self) -> None:
        self.fake_supabase.sessions["115"] = make_session(
            115,
            intent_current="alta_cliente",
            service_area="new_client",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="compartir_formulario_registro_cliente",
            last_bot_message=main.NEW_CLIENT_REGISTRATION_MESSAGE,
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=[],
                reply=main.NEW_CLIENT_REGISTRATION_MESSAGE,
            )
        )

        main.handle_telegram_message(115, "Ya lo completé pelotuda")

        sent = self.fake_telegram.messages[-1][1]
        self.assertEqual(sent, main.NEW_CLIENT_POST_REGISTRATION_MESSAGE)
        self.assertNotIn(main.NEW_CLIENT_REGISTRATION_FORM_URL, sent)

    def test_registration_completed_resumes_pending_route_flow(self) -> None:
        self.fake_supabase.sessions["116"] = make_session(
            116,
            intent_current="alta_cliente",
            service_area="new_client",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="compartir_formulario_registro_cliente",
            captured_fields={
                "post_registration_service_area": "route_scheduling",
                "post_registration_intent": "programacion_rutas",
            },
            last_bot_message=main.NEW_CLIENT_REGISTRATION_MESSAGE,
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=[],
                reply=main.NEW_CLIENT_REGISTRATION_MESSAGE,
            )
        )

        main.handle_telegram_message(116, "ya lo complete")

        sent = self.fake_telegram.messages[-1][1]
        self.assertEqual(sent, main.NEW_CLIENT_POST_REGISTRATION_ROUTE_MESSAGE)
        self.assertNotIn(main.NEW_CLIENT_REGISTRATION_FORM_URL, sent)

        stored = self.fake_supabase.sessions["116"]
        self.assertEqual(stored["service_area"], "route_scheduling")
        self.assertEqual(stored["intent_current"], "programacion_rutas")
        self.assertEqual(stored["next_action"], "solicitar_nif_o_nombre_fiscal")
        self.assertNotIn("post_registration_service_area", stored.get("captured_fields", {}))

    def test_new_client_intent_shares_registration_form(self) -> None:
        self.fake_supabase.sessions["107"] = make_session(107)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                reply="Perfecto, te ayudo con eso.",
            )
        )
        main.handle_telegram_message(107, "quiero registrarme")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn(main.NEW_CLIENT_REGISTRATION_FORM_URL, sent)

    def test_accounting_intent_not_blocked_by_route_identification_gate(self) -> None:
        self.fake_supabase.sessions["108"] = make_session(108)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="contabilidad",
                service_area="accounting",
                missing_fields=[],
                reply="Te comunico con contabilidad para ayudarte con la factura.",
            )
        )
        main.handle_telegram_message(108, "necesito contabilidad")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn("contabilidad", sent.lower())
        self.assertNotIn("nif", sent.lower())

    def test_results_reference_advances_flow_and_captures_identifier(self) -> None:
        self.fake_supabase.sessions["109"] = make_session(109)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="resultados",
                service_area="results",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                missing_fields=["numero de muestra o nombre mascota"],
                reply="Gracias. Reviso el estado.",
            )
        )
        main.handle_telegram_message(109, "resultados mi muestra es 12345")
        sent = self.fake_telegram.messages[-1][1]
        self.assertIn("ya tengo ese dato", sent.lower())
        stored = self.fake_supabase.sessions["109"]
        self.assertEqual(stored["captured_fields"].get("sample_reference"), "12345")

    def test_unknown_intent_triggers_clarification_message(self) -> None:
        self.fake_supabase.sessions["110"] = make_session(110)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                reply="No entendi.",
            )
        )
        main.handle_telegram_message(110, "necesito algo")
        self.assertEqual(self.fake_telegram.messages[-1][1], main.INTENT_CLARIFICATION_MESSAGE)

    def test_greeting_only_does_not_force_previous_results_context(self) -> None:
        self.fake_supabase.sessions["112"] = make_session(
            112,
            intent_current="resultados",
            service_area="results",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            missing_fields=["nombre de la clinica veterinaria"],
            last_bot_message="Para ayudarte con los resultados, dime tu clinica.",
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="resultados",
                service_area="results",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=["nombre de la clinica veterinaria"],
                reply="Para ayudarte con los resultados, por favor indicame el nombre de tu clinica veterinaria.",
            )
        )

        main.handle_telegram_message(112, "Hola buenas tardes")

        self.assertEqual(self.fake_telegram.messages[-1][1], main.INTENT_CLARIFICATION_MESSAGE)

    def test_detect_explicit_service_area_handles_grammar_variation(self) -> None:
        detected = main.detect_explicit_service_area("necesito mandar una muestras a analizar")
        self.assertEqual(detected, "route_scheduling")

    def test_detect_explicit_service_area_handles_registrame_typo(self) -> None:
        detected = main.detect_explicit_service_area("necesito registrame")
        self.assertEqual(detected, "new_client")


if __name__ == "__main__":
    unittest.main()
