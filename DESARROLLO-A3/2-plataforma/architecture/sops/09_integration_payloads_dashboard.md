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

## Dashboard Clients Payload (V1.4)

Endpoint: `GET /api/dashboard/overview`

Campos agregados para perfil comercial/facturacion y asignacion manual de motorizado:

```json
{
  "summary": {
    "clients_with_profile": 182,
    "new_clients_indexed": 39
  },
  "clients_rows": [
    {
      "client_id": "uuid-client",
      "clinic_key": "clinica-demo",
      "display_name": "Clinica Demo Norte",
      "secondary_name": "Clinica Demo",
      "client_code": "A3-1022",
      "client_type": "empresa",
      "clinic_name": "Clinica Demo",
      "tax_id": "900123456",
      "phone": "3001234567",
      "email": "contacto@clinicademo.com",
      "billing_email": "facturas@clinicademo.com",
      "vat_regime": "responsable_iva",
      "electronic_invoicing": true,
      "invoicing_rut_url": "https://.../rut.pdf",
      "registration_timestamp": "2026-04-14T10:22:00",
      "registration_date": "2026-04-14",
      "registration_time": "10:22",
      "observations": "Cliente activo con FE mensual",
      "entered_flag": true,
      "assigned_courier_id": "uuid-courier",
      "courier_name": "Carlos Rios",
      "client_status": "Activo",
      "requests_count": 7,
      "samples_count": 4,
      "latest_request_status": "assigned",
      "latest_sample_status": "in_analysis"
    }
  ]
}
```

### Fallback Rules (clients)

- Si `clients_a3_knowledge` o `clients_a3_professionals` no estan disponibles, el dashboard debe cargar con datos de `clients`.
- El cruce de datos se hace por `clinic_key` normalizado y fallback por telefono/nombre.
- Nunca bloquear la carga de `/dashboard` o `/clientes` por ausencia de tablas de integracion.

## Dashboard Editable Endpoints (V1.4)

### Update profile field

Endpoint: `POST /api/dashboard/client-profile`

```json
{
  "clinic_key": "clinica-demo",
  "clinic_name": "Clinica Demo",
  "field": "electronic_invoicing",
  "value": "si"
}
```

Allowed `field` values:
- `client_code`
- `commercial_name`
- `client_type` (`es_persona`, `empresa`, `otro`, empty)
- `billing_email`
- `vat_regime` (`no_responsable_iva`, `responsable_iva`, empty)
- `electronic_invoicing` (`si`, `no`, empty)
- `invoicing_rut_url`
- `observations`
- `entered_flag` (`si`, `no`, empty)

### Update courier assignment

Endpoint: `POST /api/dashboard/client-assignment`

```json
{
  "client_id": "uuid-client",
  "courier_id": "uuid-courier"
}
```

- `courier_id` empty (`""`) clears current assignment.

### Update request status (manual dashboard)

Endpoint: `POST /api/dashboard/request-status`

```json
{
  "request_id": "uuid-request",
  "status": "on_route"
}
```

Allowed `status` values:
- `received`
- `assigned`
- `on_route`
- `picked_up`
- `in_lab`
- `processed`
- `sent`
- `cancelled`
- `error_pending_assignment`

### Update sample status (manual dashboard)

Endpoint: `POST /api/dashboard/sample-status`

```json
{
  "sample_id": "uuid-sample",
  "status": "in_analysis"
}
```

Allowed `status` values:
- `pending_pickup`
- `on_route`
- `received_lab`
- `in_analysis`
- `ready_results`
- `delivered_results`
- `cancelled`

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
