import unittest

from app import main


class FakeSupabase:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.message_events: list[dict] = []
        self.request_events: list[dict] = []
        self.requests_by_id: dict[str, dict] = {}
        self.request_counter = 0
        self.clients_by_tax: dict[str, dict] = {}
        self.clients: list[dict] = []
        self.knowledge_clients: list[dict] = []
        self.knowledge_sample_events: dict[str, list[dict]] = {}
        self.table_rows: dict[str, list[dict]] = {}
        self.client_courier_map: dict[str, dict] = {}
        self.catalog_tests: list[dict] = []

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

    def search_a3_knowledge_by_clinic_name(self, clinic_name: str, limit: int = 5):
        needle = (clinic_name or "").strip().lower()
        matches = [
            row
            for row in self.knowledge_clients
            if needle and needle in (row.get("clinic_name") or "").lower()
        ]
        return matches[:limit]

    def list_a3_sample_events(self, clinic_key: str, limit: int = 200):
        rows = self.knowledge_sample_events.get(clinic_key, [])
        return rows[:limit]

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
        created = {"id": f"req-{self.request_counter}", **payload}
        self.requests_by_id[created["id"]] = created
        return created

    def create_request_event(self, request_id: str, event_type: str, event_payload: dict):
        event = {
            "request_id": request_id,
            "event_type": event_type,
            "event_payload": event_payload,
        }
        self.request_events.append(event)
        return event

    def update_request(self, request_id: str, payload: dict):
        existing = self.requests_by_id.get(request_id, {"id": request_id})
        existing.update(payload)
        self.requests_by_id[request_id] = existing
        return existing

    def get_assigned_courier(self, client_id: str):
        return self.client_courier_map.get(client_id)

    def list_catalog_tests(self, limit: int = 3000):
        return self.catalog_tests[:limit]

    def create_conversation_stage_event(self, payload: dict):
        return payload

    def insert_rows(self, table: str, rows: list[dict], upsert: bool = False, on_conflict: str | None = None):
        bucket = self.table_rows.setdefault(table, [])
        if table == "clients_a3_knowledge":
            for row in rows:
                clinic_key = row.get("clinic_key")
                if clinic_key:
                    self.knowledge_clients = [
                        existing for existing in self.knowledge_clients if existing.get("clinic_key") != clinic_key
                    ]
                    self.knowledge_clients.append(dict(row))
        for row in rows:
            bucket.append(dict(row))
            if table == "clients":
                self.clients.append(dict(row))
        return rows


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
        self.original_new_client_secret = main.settings.new_client_form_webhook_secret

        self.fake_supabase = FakeSupabase()
        self.fake_telegram = FakeTelegram()
        main.supabase = self.fake_supabase
        main.telegram = self.fake_telegram

    def tearDown(self) -> None:
        main.supabase = self.original_supabase
        main.telegram = self.original_telegram
        main.openai_service = self.original_openai
        main.settings.new_client_form_webhook_secret = self.original_new_client_secret

    def _set_unknown_openai(self) -> None:
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                missing_fields=[],
                reply="Entiendo, te ayudo con gusto.",
            )
        )

    def _seed_catalog(self) -> None:
        self.fake_supabase.catalog_tests = [
            {
                "test_code": "101",
                "test_name": "Hemograma canino",
                "category": "Hematologia",
                "subcategory": "24 horas",
                "sample_type": "Sangre",
                "price_cop": 55000,
                "turnaround_hours": 24,
                "is_active": True,
            },
            {
                "test_code": "202",
                "test_name": "Perfil renal",
                "category": "Quimica sanguinea",
                "subcategory": "48 horas",
                "sample_type": "Suero",
                "price_cop": 85000,
                "turnaround_hours": 48,
                "is_active": True,
            },
            {
                "test_code": "303",
                "test_name": "Coprologico",
                "category": "Coprologia",
                "subcategory": "24 horas",
                "sample_type": "Materia fecal",
                "price_cop": 40000,
                "turnaround_hours": 24,
                "is_active": True,
            },
        ]

    def _seed_catalog_extended(self) -> None:
        self.fake_supabase.catalog_tests = [
            {
                "test_code": "1102",
                "test_name": "Prueba Cruzada de Coombs Tubos Tapa Morada y Tapa Roja",
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
                "test_code": "1902",
                "test_name": "Citologia Malassezia y oido Enviar 2 Laminas",
                "category": "D.C.",
                "subcategory": "3 horas a partir de ingreso al laboratorio",
                "sample_type": "laminas/citologia",
                "price_cop": 15000,
                "turnaround_hours": 3,
                "is_active": True,
            },
            {
                "test_code": "1903",
                "test_name": "Citologia PAF Enviar 3 Laminas",
                "category": "D.C.",
                "subcategory": "8 dias habiles a partir de ingreso al laboratorio",
                "sample_type": "laminas/citologia",
                "price_cop": 52000,
                "turnaround_hours": 192,
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
            {
                "test_code": "2208",
                "test_name": "SDMA - Vcheck Tubo Rojo o Amarillo",
                "category": "PRUEBAS ESPECIFICAS VCHECK",
                "subcategory": "El mismo dia",
                "sample_type": "sangre",
                "price_cop": 159000,
                "turnaround_hours": 8,
                "is_active": True,
            },
        ]

    def _build_variants(self, bases: list[str]) -> list[str]:
        prefixes = [
            "hola",
            "hola buen dia",
            "buenas",
            "buenas tardes",
            "que tal",
            "porfa",
            "necesito ayuda",
            "me ayudas",
            "hola como estan",
            "",
        ]
        suffixes = [
            "por favor",
            "gracias",
            "cuando puedas",
            "",
            "es urgente",
        ]

        variants: list[str] = []
        for i in range(50):
            prefix = prefixes[i % len(prefixes)].strip()
            base = bases[i % len(bases)].strip()
            suffix = suffixes[(i * 2) % len(suffixes)].strip()
            parts = [part for part in (prefix, base, suffix) if part]
            variants.append(" ".join(parts))
        return variants

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

    def test_route_registered_phrase_keeps_route_flow_and_identifies_clinic(self) -> None:
        self.fake_supabase.sessions["116"] = make_session(
            116,
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="solicitar_nif_o_nombre_fiscal",
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-terra",
                "clinic_name": "Terra Pets",
                "phone": "+573001234567",
                "tax_id": "900123456",
                "address": "CL 2 87F 31",
            }
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="alta_cliente",
                service_area="new_client",
                next_action="solicitar_tipo_cliente",
                reply="Te ayudo con registro.",
            )
        )

        main.handle_telegram_message(116, "si estoy registrado, Terra Pets es la veterinaria")

        stored = self.fake_supabase.sessions["116"]
        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertEqual(stored["service_area"], "route_scheduling")
        self.assertNotIn("formulario", sent)
        self.assertIn("terra pets", sent)

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

    def test_prueba_a_analizar_phrase_goes_to_identification_gate(self) -> None:
        self.fake_supabase.sessions["114"] = make_session(114)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                reply="Entiendo.",
            )
        )
        main.handle_telegram_message(114, "necesito mandar una prueba a analizar")
        self.assertEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)
        stored = self.fake_supabase.sessions["114"]
        self.assertEqual(stored["service_area"], "route_scheduling")

    def test_semantic_hint_routes_unknown_phrase_to_route(self) -> None:
        class SemanticOpenAI(FakeOpenAI):
            def classify_service_area(self, *, user_message: str):
                return "route_scheduling"

        self.fake_supabase.sessions["115"] = make_session(115)
        main.openai_service = SemanticOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                reply="Entiendo.",
            )
        )

        main.handle_telegram_message(115, "quisiera coordinar una analitica veterinaria domiciliaria")

        stored = self.fake_supabase.sessions["115"]
        self.assertEqual(stored["service_area"], "route_scheduling")
        self.assertEqual(stored["next_action"], "solicitar_nif_o_nombre_fiscal")

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
        self.assertIn("registro", sent.lower())
        stored = self.fake_supabase.sessions["104"]
        self.assertEqual(stored["service_area"], "new_client")
        self.assertEqual(stored["next_action"], "solicitar_tipo_cliente")

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
        self.assertTrue("confirma" in sent.lower() or "indica" in sent.lower() or "trabajas como" in sent.lower())

    def test_registration_completed_message_moves_to_classification(self) -> None:
        self.fake_supabase.sessions["114"] = make_session(
            114,
            intent_current="alta_cliente",
            service_area="new_client",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="solicitar_tipo_cliente",
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
        self.assertNotIn("formulario", sent.lower())
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
            next_action="solicitar_tipo_cliente",
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
        self.assertNotIn("formulario", sent.lower())

    def test_registration_completed_resumes_pending_route_flow(self) -> None:
        self.fake_supabase.sessions["116"] = make_session(
            116,
            intent_current="alta_cliente",
            service_area="new_client",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="solicitar_tipo_cliente",
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
        self.assertNotIn("formulario", sent.lower())

        stored = self.fake_supabase.sessions["116"]
        self.assertEqual(stored["service_area"], "route_scheduling")
        self.assertEqual(stored["intent_current"], "programacion_rutas")
        self.assertEqual(stored["next_action"], "solicitar_nif_o_nombre_fiscal")
        self.assertNotIn("post_registration_service_area", stored.get("captured_fields", {}))

    def test_new_client_intent_starts_chat_onboarding(self) -> None:
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
        self.assertIn("registro", sent.lower())
        stored = self.fake_supabase.sessions["107"]
        self.assertEqual(stored["next_action"], "solicitar_tipo_cliente")

    def test_new_client_profile_reply_does_not_jump_to_route_flow(self) -> None:
        self.fake_supabase.sessions["1071"] = make_session(
            1071,
            intent_current="alta_cliente",
            service_area="new_client",
            next_action="solicitar_tipo_cliente",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(1071, "tengo clinica veterinaria")

        sent = self.fake_telegram.messages[-1][1].lower()
        stored = self.fake_supabase.sessions["1071"]
        self.assertEqual(stored["service_area"], "new_client")
        self.assertEqual(stored["captured_fields"].get("new_client_profile_type"), "clinica")
        self.assertEqual(stored["next_action"], "solicitar_nombre_razon_social")
        self.assertIn("razon social", sent)
        self.assertNotIn("nif", sent)

    def test_new_client_repeated_segment_message_gets_specific_prompt(self) -> None:
        self.fake_supabase.sessions["1072"] = make_session(
            1072,
            intent_current="alta_cliente",
            service_area="new_client",
            next_action="solicitar_tipo_cliente",
            last_bot_message="Para continuar el alta, confirma si eres 1) Clinica veterinaria o 2) Medico veterinario independiente.",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(1072, "soy cliente nuevo")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("trabajas como", sent)
        self.assertIn("clinica veterinaria", sent)

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
        self.assertIn("dato recibido", sent.lower())
        stored = self.fake_supabase.sessions["109"]
        self.assertEqual(stored["captured_fields"].get("sample_reference"), "12345")

    def test_results_non_canonical_next_action_is_normalized(self) -> None:
        self.fake_supabase.sessions["1091"] = make_session(1091)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="resultados",
                service_area="results",
                next_action="Solicitar identificacion de la muestra o mascota para consulta de resultados.",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                missing_fields=["numero de muestra o nombre mascota"],
                reply="Perfecto, vamos a consultar resultados.",
            )
        )

        main.handle_telegram_message(1091, "consulta de resultados")

        stored = self.fake_supabase.sessions["1091"]
        self.assertEqual(stored["service_area"], "results")
        self.assertEqual(stored["next_action"], "continuar_conversacion")

    def test_route_non_canonical_next_action_is_normalized(self) -> None:
        self.fake_supabase.sessions["1092"] = make_session(
            1092,
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            client_id="client-1",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "CL 2 87F 31",
            },
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                next_action="Confirmar direccion de retiro con el cliente",
                phase_current="fase_3_validacion",
                phase_next="fase_4_confirmacion",
                missing_fields=[],
                reply="Perfecto, confirmemos direccion.",
            )
        )

        main.handle_telegram_message(1092, "programar recogida")

        sent = self.fake_telegram.messages[-1][1].lower()
        stored = self.fake_supabase.sessions["1092"]
        self.assertEqual(stored["next_action"], "confirmar_direccion_retiro")
        self.assertIn("direccion habitual", sent)

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
        self.assertEqual(self.fake_telegram.messages[-1][1], main.ACCESS_SEGMENT_CLARIFICATION_MESSAGE)

    def test_clarification_menu_includes_operational_options(self) -> None:
        menu = main.INTENT_CLARIFICATION_MESSAGE
        self.assertIn("programar recogida", menu.lower())
        self.assertIn("resultados", menu.lower())
        self.assertIn("pagos", menu.lower())
        self.assertIn("pqrs", menu.lower())

    def test_pqrs_option_shares_link_and_returns_menu(self) -> None:
        self.fake_supabase.sessions["117"] = make_session(117)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                reply="Entiendo.",
            )
        )

        main.handle_telegram_message(117, "pqrs")

        self.assertGreaterEqual(len(self.fake_telegram.messages), 2)
        first_reply = self.fake_telegram.messages[-2][1]
        second_reply = self.fake_telegram.messages[-1][1]
        self.assertIn(main.PQRS_LINK_URL, first_reply)
        self.assertEqual(second_reply, main.INTENT_CLARIFICATION_MESSAGE)

    def test_other_queries_option_requests_detail(self) -> None:
        self.fake_supabase.sessions["118"] = make_session(118)
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="no_clasificado",
                service_area="unknown",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                reply="Entiendo.",
            )
        )

        main.handle_telegram_message(118, "otras consultas")

        self.assertEqual(self.fake_telegram.messages[-1][1], main.OTHER_QUERIES_MESSAGE)
        stored = self.fake_supabase.sessions["118"]
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_catalog_price_question_returns_specific_value_when_match_exists(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["140"] = make_session(140)
        self._set_unknown_openai()

        main.handle_telegram_message(140, "cuanto cuesta el perfil renal?")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("perfil renal", sent)
        self.assertIn("85.000", sent)
        self.assertTrue("valor referencial" in sent or "codigo" in sent)
        stored = self.fake_supabase.sessions["140"]
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_catalog_general_services_question_returns_categories(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["141"] = make_session(141)
        self._set_unknown_openai()

        main.handle_telegram_message(141, "que tipos de analisis manejan?")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertTrue("manejamos servicios" in sent or "catalogo" in sent or "tiempo estimado" in sent)
        self.assertIn("hematologia", sent)
        self.assertIn("codigo", sent)

    def test_catalog_question_keeps_unknown_when_openai_turn_fails(self) -> None:
        class FailingSemanticOpenAI:
            model = "failing-semantic-openai"

            def __init__(self) -> None:
                self.classify_calls = 0

            def generate_turn(self, system_prompt: str, user_message: str, state: dict):
                _ = (system_prompt, user_message, state)
                raise ValueError("invalid openai payload")

            def classify_service_area(self, *, user_message: str):
                _ = user_message
                self.classify_calls += 1
                return "results"

        main.register_openai_success()
        self._seed_catalog()
        self.fake_supabase.sessions["1411"] = make_session(1411)
        failing_openai = FailingSemanticOpenAI()
        main.openai_service = failing_openai

        try:
            main.handle_telegram_message(1411, "quiero consultarte sobre que analisis realizan primeramente")
        finally:
            main.register_openai_success()

        sent = self.fake_telegram.messages[-1][1].lower()
        stored = self.fake_supabase.sessions["1411"]

        self.assertTrue("servicios" in sent or "catalogo" in sent or "valor referencial" in sent)
        self.assertNotIn("gracias, te ayudo con eso", sent)
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "atender_otra_consulta")
        self.assertEqual(failing_openai.classify_calls, 0)

    def test_openai_fallback_registers_generation_error_event(self) -> None:
        class FailingOpenAI:
            model = "failing-openai"
            fallback_model = "backup-model"

            def generate_turn(self, system_prompt: str, user_message: str, state: dict):
                _ = (system_prompt, user_message, state)
                raise ValueError("invalid json payload")

            def classify_service_area(self, *, user_message: str):
                _ = user_message
                return "unknown"

        self.fake_supabase.sessions["1412"] = make_session(1412)
        main.register_openai_success()
        main.openai_service = FailingOpenAI()

        try:
            main.handle_telegram_message(1412, "necesito ayuda con resultados")
        finally:
            main.register_openai_success()

        event_types = [row["event_type"] for row in self.fake_supabase.request_events]
        self.assertIn("openai_generation_error", event_types)

        fallback_events = [
            row
            for row in self.fake_supabase.request_events
            if row.get("event_type") == "openai_generation_error"
        ]
        self.assertTrue(fallback_events)
        payload = fallback_events[-1]["event_payload"]
        self.assertIn("generation_error", payload.get("reason", ""))
        self.assertTrue(payload.get("fallback_used"))

    def test_route_time_window_alias_from_openai_is_mapped(self) -> None:
        self.fake_supabase.sessions["1413"] = make_session(
            1413,
            client_id="client-1413",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            phase_current="fase_2_recogida_datos",
            phase_next="fase_3_validacion",
            next_action="solicitar_cliente_y_direccion",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "Cra 12 # 34-56",
            },
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-1413",
                "clinic_name": "Terra Pets",
                "address": "Cra 12 # 34-56",
                "phone": "+573001234567",
                "tax_id": "900123456",
            }
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                next_action="confirmar_direccion_retiro",
                captured_fields={"time_window": "jornada de la tarde"},
                reply="Perfecto, te ayudo con eso.",
            )
        )

        main.handle_telegram_message(1413, "ok")

        stored = self.fake_supabase.sessions["1413"]
        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertEqual(stored["captured_fields"].get("pickup_time_window"), "jornada de la tarde")
        self.assertEqual(stored["captured_fields"].get("time_window"), "jornada de la tarde")
        self.assertIn("franja jornada de la tarde", sent)

    def test_enforce_reply_quality_for_unknown_returns_menu(self) -> None:
        response = main.enforce_service_area_reply_quality(
            service_area="unknown",
            reply="Gracias, te ayudo con eso.",
            missing_fields=[],
        )
        self.assertEqual(response, main.INTENT_CLARIFICATION_MESSAGE)

    def test_openai_warmup_failure_does_not_open_circuit(self) -> None:
        class FailingHealthOpenAI:
            def quick_health_check(self, *, timeout: int = 4) -> bool:
                _ = timeout
                return False

        previous_warmup = main.OPENAI_WARMUP_DONE
        previous_streak = main.OPENAI_FAILURE_STREAK
        previous_until = main.OPENAI_CIRCUIT_UNTIL
        previous_openai = main.openai_service

        main.OPENAI_WARMUP_DONE = False
        main.OPENAI_FAILURE_STREAK = 0
        main.OPENAI_CIRCUIT_UNTIL = 0.0
        main.openai_service = FailingHealthOpenAI()

        try:
            main.ensure_openai_warmup()
            self.assertEqual(main.OPENAI_FAILURE_STREAK, 0)
            self.assertFalse(main.openai_circuit_active())
        finally:
            main.OPENAI_WARMUP_DONE = previous_warmup
            main.OPENAI_FAILURE_STREAK = previous_streak
            main.OPENAI_CIRCUIT_UNTIL = previous_until
            main.openai_service = previous_openai

    def test_catalog_unknown_exam_asks_for_specific_name_or_code(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["142"] = make_session(142)
        self._set_unknown_openai()

        main.handle_telegram_message(142, "precio de examen ultra hiper complejo")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("codigo", sent)
        self.assertIn("valor referencial", sent)

    def test_catalog_orina_query_groups_by_sample_type(self) -> None:
        self.fake_supabase.catalog_tests = [
            {
                "test_code": "2102",
                "test_name": "Urocultivo y Antibiograma Orina Fresca y Esteril",
                "category": "D.C.",
                "subcategory": "Dependiendo del Cultivo",
                "sample_type": None,
                "price_cop": 80000,
                "is_active": True,
            },
            {
                "test_code": "1309",
                "test_name": "Creatinina Tubo Rojo o Amarillo",
                "category": "D.C.",
                "subcategory": "3 horas a partir de ingreso al laboratorio",
                "sample_type": None,
                "price_cop": 12000,
                "is_active": True,
            },
        ]
        self.fake_supabase.sessions["1421"] = make_session(1421)
        self._set_unknown_openai()

        main.handle_telegram_message(1421, "que analisis de orina tienen y que precio?")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("orina", sent)
        self.assertIn("urocultivo", sent)

    def test_catalog_specific_exam_includes_collection_details(self) -> None:
        self.fake_supabase.catalog_tests = [
            {
                "test_code": "1102",
                "test_name": "Prueba Cruzada de Coombs Tubos Tapa Morada y Tapa Roja",
                "category": "D.C.",
                "subcategory": "3 horas a partir de ingreso al laboratorio",
                "sample_type": None,
                "price_cop": 28000,
                "is_active": True,
            }
        ]
        self.fake_supabase.sessions["1422"] = make_session(1422)
        self._set_unknown_openai()

        main.handle_telegram_message(1422, "precio coombs")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("tapa morada", sent)
        self.assertIn("tapa roja", sent)
        self.assertIn("28.000", sent)

    def test_catalog_stress_variants_understand_synonyms_and_tone(self) -> None:
        self._seed_catalog_extended()
        self._set_unknown_openai()

        cases = [
            (
                "orina",
                [
                    "que examenes de orina manejan?",
                    "soy vet, que prueba urinaria recomiendas?",
                    "necesito uro cultivo, costo y toma",
                    "quiero saber analisis urinarios y tiempos",
                    "que hacen para muestra de orina",
                ],
            ),
            (
                "materia fecal",
                [
                    "precio coprologico",
                    "manejan copro?",
                    "opciones para materia fecal",
                    "soy clinico, necesito copro y tiempo de entrega",
                    "analisis de heces disponibles",
                ],
            ),
            (
                "sangre",
                [
                    "precio de coombs",
                    "que pruebas de sangre tienen",
                    "soy veterinario, necesito creatinina urgente",
                    "manejan perfiles sanguineos?",
                    "costos de analisis en tubo tapa roja",
                ],
            ),
            (
                "laminas",
                [
                    "citologia de oido costo",
                    "analisis por laminas",
                    "que hacen con paf",
                    "opciones de citologia veterinaria",
                    "envio 2 laminas, me ayudas con valor",
                ],
            ),
        ]

        chat_id = 3000
        for expected_keyword, prompts in cases:
            for prompt in prompts:
                chat_id += 1
                self.fake_supabase.sessions[str(chat_id)] = make_session(chat_id)
                main.handle_telegram_message(chat_id, prompt)
                sent = self.fake_telegram.messages[-1][1].lower()

                with self.subTest(prompt=prompt):
                    self.assertTrue(
                        "servicios" in sent
                        or "catalogo" in sent
                        or "valor referencial" in sent
                        or "codigo" in sent
                    )
                    self.assertTrue(
                        any(token in sent for token in ("valor referencial", "tiempo estimado", "toma recomendada"))
                    )
                    self.assertIn(expected_keyword, sent)

    def test_numeric_menu_option_routes_to_pickup_flow(self) -> None:
        self.fake_supabase.sessions["119"] = make_session(119)
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(119, "1")

        self.assertEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)
        stored = self.fake_supabase.sessions["119"]
        self.assertEqual(stored["service_area"], "route_scheduling")

    def test_route_can_progress_with_clinic_found_in_knowledge_index(self) -> None:
        self.fake_supabase.sessions["120"] = make_session(120)
        self.fake_supabase.knowledge_clients = [
            {
                "clinic_key": "animal consult",
                "clinic_name": "Animal Consult",
                "address": "Cra 10 # 20-30",
                "phone": "3000000000",
            }
        ]
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(120, "quiero programar recogida, mi veterinaria es animal consult")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("direccion habitual", sent)
        self.assertNotEqual(self.fake_telegram.messages[-1][1], main.ROUTE_CLIENT_IDENTIFICATION_MESSAGE)
        stored = self.fake_supabase.sessions["120"]
        self.assertEqual(stored["service_area"], "route_scheduling")
        self.assertEqual(stored["captured_fields"].get("clinic_name"), "Animal Consult")

    def test_results_uses_knowledge_summary_when_clinic_detected(self) -> None:
        self.fake_supabase.sessions["121"] = make_session(
            121,
            captured_fields={
                "clinic_name": "My Pet City",
                "knowledge_clinic_key": "my pet city",
            },
        )
        self.fake_supabase.knowledge_sample_events = {
            "my pet city": [
                {"status_bucket": "pending_issue", "reason": "No Envian"},
                {"status_bucket": "pending_issue", "reason": "No Envian"},
                {"status_bucket": "submitted", "reason": ""},
            ]
        }
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="resultados",
                service_area="results",
                phase_current="fase_1_clasificacion",
                phase_next="fase_2_recogida_datos",
                missing_fields=["numero de muestra o nombre mascota"],
                reply="Te ayudo con resultados.",
            )
        )

        main.handle_telegram_message(121, "consulta de resultados")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("trazabilidad", sent)
        self.assertIn("novedad", sent)
        self.assertIn("numero de muestra", sent)

    def test_route_confirmation_creates_mock_submission_event(self) -> None:
        self.fake_supabase.sessions["122"] = make_session(
            122,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="confirmar_direccion_retiro",
            captured_fields={
                "clinic_name": "Vet Norte",
                "pickup_address": "Cra 10 # 12-34",
            },
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-1",
                "clinic_name": "Vet Norte",
                "address": "Cra 10 # 12-34",
                "phone": "+573001112233",
                "tax_id": "900123456",
            }
        )
        self.fake_supabase.client_courier_map["client-1"] = {
            "id": "courier-1",
            "name": "Alexander",
            "phone": "000123",
            "availability": "available",
        }
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_4_confirmacion",
                phase_next="fase_5_programacion_ruta",
                next_action="confirmar_programacion_ruta",
                missing_fields=[],
                reply="Listo, tu solicitud de retiro de muestra quedo programada.",
            )
        )

        main.handle_telegram_message(122, "si confirmo")

        event_types = [row["event_type"] for row in self.fake_supabase.request_events]
        self.assertIn("route_form_mock_submitted", event_types)
        self.assertIn("assignment_result", event_types)
        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("mensajero asignado", sent)

    def test_route_negative_confirmation_requests_updated_address(self) -> None:
        self.fake_supabase.sessions["123"] = make_session(
            123,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="confirmar_direccion_retiro",
            captured_fields={
                "clinic_name": "Vet Norte",
                "pickup_address": "Cra 10 # 12-34",
            },
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-1",
                "clinic_name": "Vet Norte",
                "address": "Cra 10 # 12-34",
                "phone": "+573001112233",
                "tax_id": "900123456",
            }
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_4_confirmacion",
                phase_next="fase_5_programacion_ruta",
                next_action="confirmar_direccion_retiro",
                missing_fields=["confirmacion de direccion"],
                reply="Perfecto, te ayudo con la programacion de ruta.",
            )
        )

        main.handle_telegram_message(123, "no, cambiar direccion")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("direccion actual", sent)
        stored = self.fake_supabase.sessions["123"]
        self.assertEqual(stored["next_action"], "solicitar_direccion_actualizada")

    def test_route_already_programmed_does_not_repeat_address_confirmation(self) -> None:
        self.fake_supabase.sessions["124"] = make_session(
            124,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="confirmar_programacion_ruta",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "CL 2 87F 31",
            },
            last_bot_message="Listo, tu solicitud de retiro de muestra quedo programada.",
        )
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_6_cierre",
                phase_next="fase_6_cierre",
                next_action="continuar_conversacion",
                missing_fields=[],
                reply="Perfecto, te ayudo con eso.",
            )
        )

        main.handle_telegram_message(124, "si ya lo tengo")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("solicitud programada", sent)
        self.assertNotIn("direccion habitual", sent)
        self.assertNotIn("recordatorio", sent)
        stored = self.fake_supabase.sessions["124"]
        self.assertEqual(stored["next_action"], "continuar_conversacion")

    def test_route_affirmative_phrase_with_registered_address_confirms_schedule(self) -> None:
        self.fake_supabase.sessions["127"] = make_session(
            127,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="confirmar_direccion_retiro",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "CL 2 87F 31",
            },
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-1",
                "clinic_name": "Terra Pets",
                "address": "CL 2 87F 31",
                "phone": "+573001112233",
                "tax_id": "1070977829-7",
            }
        )
        self.fake_supabase.client_courier_map["client-1"] = {
            "id": "courier-1",
            "name": "Alexander",
            "phone": "000123",
            "availability": "available",
        }
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=["direccion de recogida"],
                next_action="solicitar_nif_o_nombre_fiscal",
                reply="Perfecto, te ayudo con eso.",
            )
        )

        main.handle_telegram_message(127, "ya tienen mi direccion registrada")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("quedo programada", sent)
        self.assertIn("retiro estimado es para", sent)
        stored = self.fake_supabase.sessions["127"]
        self.assertEqual(stored["next_action"], "confirmar_programacion_ruta")

    def test_route_continuar_conversacion_state_does_not_reopen_confirmation(self) -> None:
        self.fake_supabase.sessions["128"] = make_session(
            128,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="continuar_conversacion",
            status="confirmed",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "CL 2 87F 31",
                "pickup_address_confirmed": "true",
            },
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(128, "si ya lo tengo")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("solicitud programada", sent)
        self.assertNotIn("direccion habitual", sent)
        stored = self.fake_supabase.sessions["128"]
        self.assertEqual(stored["next_action"], "continuar_conversacion")

    def test_route_continuar_conversacion_allows_price_inquiry_switch(self) -> None:
        self.fake_supabase.sessions["129"] = make_session(
            129,
            client_id="client-1",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="continuar_conversacion",
            status="confirmed",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "CL 2 87F 31",
                "pickup_address_confirmed": "true",
            },
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(129, "cuanto salen sus servicios")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertTrue("servicios" in sent or "catalogo" in sent or "valor referencial" in sent)
        stored = self.fake_supabase.sessions["129"]
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_route_identification_invalid_attempts_escalate_guidance(self) -> None:
        self.fake_supabase.sessions["125"] = make_session(
            125,
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="solicitar_nif_o_nombre_fiscal",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(125, "zida")
        first = self.fake_telegram.messages[-1][1]
        main.handle_telegram_message(125, "zida")
        second = self.fake_telegram.messages[-1][1]

        self.assertNotEqual(first, second)
        self.assertIn("nif", second.lower())
        self.assertIn("nombre fiscal", second.lower())

    def test_route_identification_price_question_switches_context(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["126"] = make_session(
            126,
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="solicitar_nif_o_nombre_fiscal",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(126, "cuanto salen sus servicios")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertTrue("servicios" in sent or "hemograma" in sent)
        stored = self.fake_supabase.sessions["126"]
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_results_context_price_question_switches_context(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["131"] = make_session(
            131,
            intent_current="resultados",
            service_area="results",
            next_action="continuar_conversacion",
            status="in_progress",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(131, "quiero saber lo que salen hacer un analisis de orina")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertTrue("servicios" in sent or "analisis" in sent)
        stored = self.fake_supabase.sessions["131"]
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_results_context_service_catalog_question_switches_context(self) -> None:
        self._seed_catalog()
        self.fake_supabase.sessions["132"] = make_session(
            132,
            intent_current="resultados",
            service_area="results",
            next_action="continuar_conversacion",
            status="in_progress",
        )
        main.openai_service = FakeOpenAI(lambda _msg, _state: make_turn())

        main.handle_telegram_message(132, "que tipo de analisis de orina hacen?")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertTrue("servicios" in sent or "catalogo" in sent or "valor referencial" in sent)
        stored = self.fake_supabase.sessions["132"]
        self.assertEqual(stored["service_area"], "unknown")
        self.assertEqual(stored["next_action"], "atender_otra_consulta")

    def test_extract_clinic_hint_from_nombre_de_veterinaria_phrase(self) -> None:
        hint = main.extract_clinic_name_hint("si estoy registrado, mi nombre de veterinaria es terra pets")
        self.assertEqual(hint, "terra pets")

    def test_extract_clinic_hint_from_registered_phrase(self) -> None:
        hint = main.extract_clinic_name_hint("si estoy registrado, Terra Pets es la veterinaria")
        self.assertEqual(hint, "Terra Pets")

    def test_extract_clinic_hint_from_name_phrase(self) -> None:
        hint = main.extract_clinic_name_hint("Terra Pets es el nombre")
        self.assertEqual(hint, "Terra Pets")

    def test_parse_clinic_and_address_from_labeled_phrase(self) -> None:
        clinic, address = main.parse_clinic_and_address_from_text(
            "mi veterinaria es Terra Pets y la direccion de retiro es Cra 9 # 12-34"
        )
        self.assertEqual(clinic, "Terra Pets")
        self.assertEqual(address, "Cra 9 # 12-34")

    def test_route_urgent_priority_is_persisted(self) -> None:
        self.fake_supabase.sessions["1338"] = make_session(
            1338,
            client_id="client-urgent",
            intent_current="programacion_rutas",
            service_area="route_scheduling",
            next_action="confirmar_direccion_retiro",
            captured_fields={
                "clinic_name": "Terra Pets",
                "pickup_address": "Cra 12 # 34-56",
            },
        )
        self.fake_supabase.clients.append(
            {
                "id": "client-urgent",
                "clinic_name": "Terra Pets",
                "address": "Cra 12 # 34-56",
                "phone": "+573001112233",
                "tax_id": "900123456",
            }
        )
        self.fake_supabase.client_courier_map["client-urgent"] = {
            "id": "courier-1",
            "name": "Alexander",
            "phone": "000123",
            "availability": "available",
        }
        main.openai_service = FakeOpenAI(
            lambda _msg, _state: make_turn(
                intent="programacion_rutas",
                service_area="route_scheduling",
                phase_current="fase_2_recogida_datos",
                phase_next="fase_3_validacion",
                missing_fields=["direccion de recogida"],
                next_action="solicitar_nif_o_nombre_fiscal",
                reply="Perfecto, te ayudo con eso.",
            )
        )

        main.handle_telegram_message(1338, "urgente, por favor programar retiro hoy mismo entre las 2 y las 4 pm")

        sent = self.fake_telegram.messages[-1][1].lower()
        self.assertIn("prioridad urgente", sent)
        self.assertIn("2:00 y 4:00 pm", sent)
        stored = self.fake_supabase.sessions["1338"]
        self.assertEqual(stored["captured_fields"].get("priority"), "urgent")
        self.assertEqual(stored["captured_fields"].get("pickup_time_window"), "entre 2:00 y 4:00 pm")
        request_row = self.fake_supabase.requests_by_id[stored["request_id"]]
        self.assertEqual(request_row.get("priority"), "urgent")

    def test_detect_route_time_window_from_colloquial_phrase(self) -> None:
        value = main.detect_route_time_window("si pueden pasar en la tarde", {})
        self.assertEqual(value, "jornada de la tarde")

    def test_new_client_registration_webhook_syncs_to_supabase_tables(self) -> None:
        main.settings.new_client_form_webhook_secret = "secret-a3"
        client = main.app.test_client()

        payload = {
            "Nombre de la veterinaria o medico veterinario": "Clinica Vet Norte",
            "Direccion y ubicacion en Google Maps": "Cra 12 # 34-56",
            "Barrio y Localidad": "Kennedy",
            "N Celular": "3001234567",
            "Email": "vetnorte@example.com",
            "Medico Veterinario": "Dra Paula Rios",
            "N Tarjeta Profesional": "TP-9988",
            "Rut": "900123456",
        }

        response = client.post(
            "/webhooks/new-client-registration",
            json=payload,
            headers={"X-New-Client-Secret": "secret-a3"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("registered_in_clients"), True)
        self.assertTrue(self.fake_supabase.table_rows.get("clients_a3_knowledge"))
        self.assertTrue(self.fake_supabase.table_rows.get("clients_a3_professionals"))
        self.assertTrue(self.fake_supabase.table_rows.get("clients"))

    def test_new_client_registration_webhook_rejects_invalid_secret(self) -> None:
        main.settings.new_client_form_webhook_secret = "secret-a3"
        client = main.app.test_client()

        response = client.post(
            "/webhooks/new-client-registration",
            json={"Nombre de la veterinaria o medico veterinario": "Clinica Vet Norte"},
            headers={"X-New-Client-Secret": "otro-secret"},
        )

        self.assertEqual(response.status_code, 401)

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

        self.assertEqual(self.fake_telegram.messages[-1][1], main.INITIAL_GREETING_MESSAGE)

    def test_wellbeing_greeting_returns_human_welcome_and_menu(self) -> None:
        self.fake_supabase.sessions["1121"] = make_session(1121)
        self._set_unknown_openai()

        main.handle_telegram_message(1121, "Hola como estan?")

        self.assertEqual(self.fake_telegram.messages[-1][1], main.INITIAL_GREETING_MESSAGE)

    def test_bulk_50_variants_per_option(self) -> None:
        self._set_unknown_openai()

        route_inputs = self._build_variants(
            [
                "quiero programar recogida",
                "necesito programar recoleccion",
                "quiero agendar retiro de muestra",
                "quiero programar un retiro",
                "necesito enviar muestras",
                "quiero mandar a analizar una muestra",
                "necesito mandar una prueba a analizar",
                "quiero enviar un examen al laboratorio",
                "quiero procesar un panel diagnostico",
                "me ayudas con la ruta",
                "quiero recoger muestra",
                "programacion de ruta",
            ]
        )
        results_inputs = self._build_variants(
            [
                "consulta de resultados",
                "quiero consultar resultados",
                "necesito estado de resultado",
                "quiero ver el estado de la muestra",
                "me ayudas con resultados",
                "resultado de mi muestra",
                "estado de resultado por favor",
                "revisar resultados",
                "dame resultados",
                "quiero resultados",
            ]
        )
        accounting_inputs = self._build_variants(
            [
                "necesito contabilidad",
                "me ayudas con facturacion",
                "tengo una duda de cartera",
                "quiero revisar pagos",
                "consulta de cobro",
                "tema financiera",
                "pregunta de factura",
                "aclarar deuda",
                "duda de pago",
                "apoyo de contabilidad",
            ]
        )
        new_client_inputs = self._build_variants(
            [
                "soy cliente nuevo",
                "quiero registrarme",
                "no estoy registrado",
                "es primera vez",
                "quiero darme de alta",
                "registro de cliente",
                "necesito registrar cliente",
                "no estoy en la base",
                "quiero registrarme",
                "primera vez con ustedes",
            ]
        )
        pqrs_inputs = self._build_variants(
            [
                "pqrs",
                "quiero poner una queja",
                "quiero hacer un reclamo",
                "tengo una sugerencia",
                "quiero radicar una peticion",
                "consulta pqrs",
                "felicitacion para el equipo",
                "deseo ingresar una peticion",
                "me apoyas con pqrs",
                "necesito canal pqrs",
            ]
        )
        other_inputs = self._build_variants(
            [
                "otras consultas",
                "quiero hacer otra consulta",
                "tengo una consulta general",
                "otra duda",
                "otra inquietud",
                "pregunta adicional",
                "informacion general",
                "orientacion general",
                "soporte general",
                "consulta distinta",
            ]
        )

        cases = [
            ("route_scheduling", "solicitar_nif_o_nombre_fiscal", route_inputs),
            ("results", None, results_inputs),
            ("accounting", None, accounting_inputs),
            ("new_client", "solicitar_tipo_cliente", new_client_inputs),
            ("unknown", "share_pqrs_link", pqrs_inputs),
            ("unknown", "atender_otra_consulta", other_inputs),
        ]

        chat_id = 2000
        for expected_area, expected_action, utterances in cases:
            self.assertEqual(len(utterances), 50)
            for utterance in utterances:
                chat_id += 1
                self.fake_supabase.sessions[str(chat_id)] = make_session(chat_id)
                start_idx = len(self.fake_telegram.messages)
                main.handle_telegram_message(chat_id, utterance)
                stored = self.fake_supabase.sessions[str(chat_id)]

                with self.subTest(area=expected_area, text=utterance):
                    self.assertEqual(stored["service_area"], expected_area)
                    if expected_action:
                        self.assertEqual(stored["next_action"], expected_action)

                    new_messages = self.fake_telegram.messages[start_idx:]
                    self.assertTrue(new_messages)

                    if expected_action == "share_pqrs_link":
                        self.assertGreaterEqual(len(new_messages), 2)
                        self.assertIn(main.PQRS_LINK_URL, new_messages[0][1])
                        self.assertEqual(new_messages[1][1], main.INTENT_CLARIFICATION_MESSAGE)
                    elif expected_action == "solicitar_tipo_cliente":
                        lower_msg = new_messages[-1][1].lower()
                        self.assertTrue(bool(lower_msg.strip()))
                    elif expected_action == "atender_otra_consulta":
                        self.assertEqual(new_messages[-1][1], main.OTHER_QUERIES_MESSAGE)
                    elif expected_area == "route_scheduling":
                        self.assertIn("nif", new_messages[-1][1].lower())

    def test_detect_explicit_service_area_handles_grammar_variation(self) -> None:
        detected = main.detect_explicit_service_area("necesito mandar una muestras a analizar")
        self.assertEqual(detected, "route_scheduling")

    def test_detect_explicit_service_area_handles_registrame_typo(self) -> None:
        detected = main.detect_explicit_service_area("necesito registrame")
        self.assertEqual(detected, "new_client")


if __name__ == "__main__":
    unittest.main()
