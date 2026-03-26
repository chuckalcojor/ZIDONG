# Project Map (Source of Truth)

## Canonical context

- Canonical repository context: `AGENTS.md` (root)
- This file is the Gemini-specific adapter and project map
- If there is a conflict between context files, `AGENTS.md` prevails

Status: V1 backend scaffold implemented. Waiting credentials and webhook URL for live Link phase.

## B.L.A.S.T. Protocol State

- Current phase: `Link (pending credentials)`
- `tools/` scripts: `ENABLED` (limited to V1 scope)
- Blueprint approved: `Yes (V1)`
- Data schema confirmed: `Yes (V1 draft locked)`

## Discovery Answers (Captured)

1. North Star
   - Build an automated operating system for the veterinary laboratory that removes manual reception and messenger assignment, reduces errors, and scales operations.

2. Integrations
   - Required: WhatsApp Business API via 360dialog, OpenAI, N8N (recommended orchestrator), Anarvet, Alegra, LiveConnect (optional/gradual replacement), Google Forms (transition support).
   - Credentials state: Mentioned as required; not yet verified in this workspace.

3. Source of Truth
   - Operationally required datasets: clients, couriers, zone-to-courier mapping, requests, and status transitions.
   - Final backend: Supabase (confirmed).

4. Delivery Payload
   - Customer channel: WhatsApp confirmations, updates, and results delivery.
   - Courier channel: WhatsApp dispatch notification with pickup details.
   - Internal channel: real-time dashboard and customer portal (phase 3).
   - Accounting/LIS payload: invoice in Alegra and order/result lifecycle with Anarvet.

5. Behavioral Rules
   - Reliability over speed; data-first implementation.
   - No coding without complete datasets and approved logic.
   - Always include human fallback for exceptions and failures.
   - Build incrementally: capture -> assignment -> notifications -> integrations -> portal.

## Data Schema (Draft for Approval)

### Core Entities

```json
{
  "Client": {
    "id": "string",
    "clinic_name": "string",
    "phone": "string",
    "address": "string",
    "zone": "string",
    "billing_type": "credit|cash",
    "is_active": "boolean"
  },
  "Courier": {
    "id": "string",
    "name": "string",
    "phone": "string",
    "zones": ["string"],
    "availability": "available|busy|offline",
    "schedule": {
      "start": "HH:mm",
      "end": "HH:mm",
      "timezone": "string"
    }
  },
  "ZoneRule": {
    "zone": "string",
    "primary_courier_id": "string",
    "backup_courier_ids": ["string"],
    "max_concurrent_pickups": "number"
  }
}
```

### Input Schema (Conversation to Request)

```json
{
  "event_id": "string",
  "channel": "whatsapp_360dialog|liveconnect|manual",
  "received_at": "ISO-8601",
  "customer_message": {
    "from_phone": "string",
    "text": "string",
    "attachments": [
      {
        "type": "image|pdf|other",
        "url": "string"
      }
    ]
  },
  "intent": "pickup_request|result_inquiry|human_support|unknown",
  "pickup_request": {
    "exam_type": "string",
    "exam_code": "string",
    "patient": {
      "name": "string",
      "species": "string",
      "sex": "string",
      "age": "string"
    },
    "priority": "normal|urgent",
    "pickup_address": "string",
    "requested_window": {
      "date": "YYYY-MM-DD",
      "from": "HH:mm",
      "to": "HH:mm"
    }
  }
}
```

### Output Payload Schema (Operational)

```json
{
  "request": {
    "id": "string",
    "client_id": "string",
    "status": "received|assigned|on_route|picked_up|in_lab|processed|sent|cancelled|error",
    "exam_type": "string",
    "exam_code": "string",
    "priority": "normal|urgent",
    "created_at": "ISO-8601",
    "courier_id": "string|null",
    "anarvet_order_id": "string|null",
    "alegra_invoice_id": "string|null"
  },
  "dispatch": {
    "assigned": "boolean",
    "rule_used": "zone_primary|zone_backup|manual_fallback",
    "courier_notification": {
      "channel": "whatsapp",
      "delivered": "boolean"
    }
  },
  "customer_response": {
    "channel": "whatsapp",
    "message_type": "confirmation|status_update|result_delivery|handoff",
    "delivered": "boolean"
  },
  "integrations": {
    "alegra": {
      "attempted": "boolean",
      "success": "boolean",
      "invoice_id": "string|null"
    },
    "anarvet": {
      "attempted": "boolean",
      "success": "boolean",
      "order_id": "string|null",
      "result_url": "string|null"
    }
  },
  "audit": {
    "errors": ["string"],
    "fallback_triggered": "boolean",
    "fallback_reason": "string|null"
  }
}
```

## Blueprint (Approved for V1)

### Scope and sequencing

1. Phase 0: data readiness and rules lock (no tool code)
2. Phase 1: chatbot capture + validation + request creation
3. Phase 2: deterministic assignment engine by zone
4. Phase 3: integrations with Anarvet and Alegra (paused for now)
5. Phase 4: dashboard and client portal
6. Phase 5: QA, training, and production trigger setup

### Non-negotiable gates

- Gate A: credentials + API reachability verified.
- Gate B: zone rules approved and tested with fallback behavior.
- Gate C: status lifecycle approved end-to-end.

### Critical business rules to finalize

- Exact zone definition and mapping ownership.
- Multiple couriers per zone policy and tie-break method.
- No-courier-available behavior (manual queue, escalation, SLA).
- Urgent vs normal priority handling.
- Pickup cutoff windows and after-hours policy.

### A.N.T. layer plan

- `architecture/`: SOPs per flow (intake, dispatch, billing, LIS sync, results delivery, incidents).
- Navigation: route payloads only through approved SOP logic.
- `tools/`: atomic Python scripts after gates are approved.

## Decisions Locked

- Central database platform: `Supabase`
- Cutoff rule: after `17:30` -> schedule next business day.
- Assignment rule: fixed courier per client; no zone tie-break in V1.
- Fallback rule: if no assigned courier, create internal platform exception.
- Dev/test channel: Telegram bot.
- Live channel strategy: keep LiveConnect number, keep customer data in Supabase.
- Accounting route in V1: handoff to human only.

## Pending Decisions Before Link Phase

- Internal notification destination for fallback cases (channel and recipients).
- Holiday calendar source for "next business day" rule.
- Result PDF sending details (template, trigger moment, retries).

## Build Artifacts (Created)

- `architecture/sops/01_scope_v1.md`
- `architecture/sops/02_supabase_model.md`
- `architecture/sops/03_conversation_telegram_v1.md`
- `architecture/sops/04_assignment_and_cutoff.md`
- `architecture/sops/05_dashboard_v1.md`
- `architecture/sops/06_qa_cases_v1.md`
- `architecture/sops/07_payload_contracts_v1.md`
- `architecture/sops/08_dashboard_ops_center.md`
- `architecture/sops/09_integration_payloads_dashboard.md`
- `architecture/sql/001_v1_core_schema.sql`
- `architecture/sql/002_dashboard_operational_schema.sql`
- `tools/intake_router.py`
- `tools/schedule_business_day.py`
- `tools/assignment_engine.py`
- `tools/import_clients_excel.py`
- `tools/import_catalog_pdf.py`
- `app/templates/login.html`
- `app/templates/dashboard.html`
- `app/static/app.css`
- `app/main.py`
- `app/config.py`
- `app/logic.py`
- `app/services/supabase_service.py`
- `app/services/telegram_service.py`
- `tools/set_telegram_webhook.py`
- `.env.example`
- `requirements.txt`
- `README.md`

## Context Handoff

- V1 backend API now receives Telegram webhook updates, routes intents deterministically, persists requests/events in Supabase, and applies assignment fallback logic.
- Project includes webhook setup helper and environment template; SQL schema is ready for Supabase execution.
- Deterministic tools and backend modules passed local script checks and Python syntax compilation.
- Next step: inject real credentials, set Telegram webhook URL, run end-to-end handshake tests against live Supabase.
- Telegram and Supabase credentials were injected into local `.env`, and live handshake checks were executed.
- Telegram API connection is valid (`A3veterinariabot` reachable); Supabase is reachable but `public.clients` does not exist yet.
- Backend framework was switched from FastAPI to Flask due Python 3.14 compatibility constraints in pinned Pydantic build chain.
- Next step: execute `architecture/sql/001_v1_core_schema.sql` in Supabase, then set webhook URL and run end-to-end message tests.
- Built private operations dashboard with session login, KPI cards, funnel, client-courier analytics, conversation tracking, sample status, and catalog preview.
- Added schema and webhook contracts for LiveConnect and Anarvet ingestion so dashboard can become the operational source of truth.
- Next step: run SQL migrations `001` + `002`, execute import scripts for clients/catalog, then connect real webhook URLs for live telemetry.
- Executed client and catalog imports against Supabase (`471` processed clients, `316` courier assignments, `137` catalog tests upserted).
- Flask dashboard app was launched successfully and health endpoint confirmed (`/health` returns `ok`).
- Next step: open `/login` demo, validate data visuals, then wire LiveConnect and Anarvet webhooks with real payloads.
- Fixed dashboard runtime error caused by Supabase relation shape (`client_courier_assignment` dict vs list) and patched parser in `app/main.py`.
- Restarted Flask server with updated code and revalidated `/health` and authenticated `/dashboard` rendering.
- Next step: user validates UI and then executes SQL `002` to unlock LiveConnect/Anarvet dashboard sections without fallback mode.
- Redesigned the platform into a modern left-sidebar experience with dedicated tabs: `Dashboard`, `Clientes`, `Muestras`, and `Analisis`.
- Main dashboard now shows only KPI metrics; detailed operational tracking moved into the specific tabs as requested.
- Restarted backend on port 8000; next step is UX validation and optional enrichment of sample lifecycle statuses from live integrations.
- Upgraded UI stack in templates with Tailwind + Alpine + ApexCharts + Lucide to achieve a polished modern aesthetic inspired by the reference.
- Added chart-driven analytics (sample status donut, service-area bars, top analyses) and preserved deterministic tab routing by server-side views.
- Next step: tune branding tokens (colors/spacing/icons) and connect live LiveConnect/Anarvet payloads to populate deeper operational details.
- Rebuilt dashboard shell to match the reference style more closely: framed blue container, dark glass panels, compact left nav, rounded widgets, and trading-style top bar.
- Fixed layout overflow by constraining tables inside scrollable containers and keeping all sections clipped within the main panel frame.
- Restarted backend with the refreshed template/CSS; next step is your visual QA pass and micro-adjustments for exact spacing/contrast preferences.
- Analysis tab was restructured to match the requested document schema: `Codigo`, `Tipo de Prueba`, `Prueba`, `Tiempo de Entrega`, and `Valor`.
- Catalog import now persists delivery-time text from PDF into Supabase and reuses it directly in UI for faithful display.
- Next step: review text fidelity against PDF and refine any category edge-cases where OCR source formatting is ambiguous.
