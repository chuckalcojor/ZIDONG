# SOP 07 - Payload Contracts (V1)

## Intake Payload

```json
{
  "channel": "telegram",
  "message": "Programacion de ruta",
  "received_at": "2026-03-19T16:20:00",
  "client_phone": "+57..."
}
```

## Routed Payload

```json
{
  "service_area": "route_scheduling|accounting|results|new_client|unknown",
  "human_handoff": true,
  "original_message": "string",
  "normalized_message": "string"
}
```

## Assignment Payload

```json
{
  "request_id": "REQ-001",
  "client_id": "CLI-001",
  "assigned_courier_id": "COU-001",
  "priority": "normal|urgent"
}
```

## Assignment Result Payload

```json
{
  "request_id": "REQ-001",
  "client_id": "CLI-001",
  "assigned": true,
  "status": "assigned|error_pending_assignment",
  "courier_id": "COU-001",
  "priority": "normal|urgent",
  "fallback_triggered": false,
  "fallback_reason": null
}
```

## Courier Locality Coverage Payload (V1.5)

```json
{
  "locality_code": "kennedy",
  "locality_name": "Kennedy",
  "courier_id": "uuid-courier",
  "assigned_by": "dashboard:operator"
}
```

Rules:
- `locality_code` pertenece al catalogo cerrado de localidades de Bogota.
- Solo se permite un motorizado por localidad (`1 localidad = 1 motorizado`).
- Si no existe cobertura para la localidad, cliente nuevo queda sin asignar.

## State Transition Rules (V1)

- `received -> assigned` when a courier exists for the client.
- `received -> error_pending_assignment` when no courier assignment exists.
- `assigned -> on_route -> picked_up -> in_lab -> processed -> sent` for successful lifecycle.
- Any state -> `cancelled` by explicit operator action.

## Conversation Stage Event Payload (V1.1)

```json
{
  "channel": "telegram",
  "external_chat_id": "123456789",
  "client_id": "uuid-client",
  "request_id": "uuid-request",
  "from_stage": "fase_1_clasificacion",
  "to_stage": "fase_2_recogida_datos",
  "trigger_source": "openai_turn",
  "trigger_message": "Necesito una ruta para hoy",
  "created_at": "2026-03-24T18:10:00"
}
```

### Conversation Stage Tracking Rules

- Source of truth for current stage: `telegram_sessions.phase_current`.
- Historical audit trail: `conversation_stage_events`.
- Create event only if stage changes (`from_stage != to_stage`).
- If stage does not change, do not create duplicate event.

## Telegram Message Event Payload (V1.2)

```json
{
  "channel": "telegram",
  "external_chat_id": "123456789",
  "client_id": "uuid-client",
  "request_id": "uuid-request",
  "direction": "user|bot|system",
  "message_text": "Necesito resultados de Rocky",
  "phase_snapshot": "fase_2_recogida_datos",
  "intent_snapshot": "resultados",
  "service_area_snapshot": "results",
  "captured_fields_snapshot": {
    "pet_name": "Rocky",
    "sample_reference": null
  },
  "metadata": {
    "message_mode": "flow_progress",
    "resume_prompt": ""
  },
  "created_at": "2026-03-24T18:20:00"
}
```

### Message History Rules

- Persist every incoming user message and every outgoing bot message.
- Keep phase/intent snapshots for each message event.
- Use `captured_fields_snapshot` plus recent message history to avoid asking for data already provided.
- If history table is unavailable, bot must continue with `telegram_sessions` fallback (no hard failure).
