# SOP 09 - Integration Payloads for Dashboard

## LiveConnect Inbound Payload

Endpoint: `POST /webhooks/liveconnect`

```json
{
  "conversation_id": "lc-123",
  "message_id": "msg-987",
  "contact": "+573001112233",
  "customer_name": "Clinica Demo",
  "open_status": "open",
  "summary": "Consulta resultados de paciente Luna",
  "direction": "inbound",
  "agent_name": null,
  "intent_tag": "result_inquiry",
  "message_text": "Hola, ya estan los resultados?",
  "timestamp": "2026-03-19T13:21:00"
}
```

## Anarvet Result Sync Payload

Endpoint: `POST /webhooks/anarvet/result`

```json
{
  "request_id": "uuid-request",
  "status": "ready_results",
  "result_url": "https://.../resultado.pdf",
  "observations": "resultado validado",
  "updated_at": "2026-03-19T15:44:00"
}
```

## Validation Rules
- Reject payload when secret header does not match configured secret (if secret configured).
- Persist full payload in event table for audit.
- Never drop status updates silently.

## Dashboard Flow Payload (V1.1)

Endpoint: `GET /api/dashboard/overview`

Campos agregados para visualizacion de flujo conversacional:

```json
{
  "flow_stage_counts": [
    {
      "stage_key": "fase_2_recogida_datos",
      "label": "Recogida de datos",
      "count": 14,
      "order": 2
    }
  ],
  "flow_transitions": [
    {
      "from_stage": "fase_1_clasificacion",
      "from_label": "Clasificacion",
      "to_stage": "fase_2_recogida_datos",
      "to_label": "Recogida de datos",
      "count": 11
    }
  ],
  "flow_sessions_rows": [
    {
      "external_chat_id": "123456789",
      "clinic_name": "Clinica Demo",
      "phase_current": "fase_2_recogida_datos",
      "phase_label": "Recogida de datos",
      "requires_handoff": false
    }
  ],
  "flow_summary": {
    "sessions_tracked": 24,
    "transitions_logged": 112,
    "sessions_handoff": 3
  }
}
```
