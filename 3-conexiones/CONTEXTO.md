# Modulo: Conexiones e Integraciones

## Responsabilidad
Modelo de datos, esquemas SQL, contratos de API y documentacion de todas las integraciones externas del sistema.

## Estructura

```
3-conexiones/
├── architecture/
│   ├── sql/
│   │   ├── 001_v1_core_schema.sql              # Tablas core: clients, couriers, requests, etc.
│   │   ├── 002_dashboard_operational_schema.sql  # Tablas para el dashboard
│   │   ├── 003_telegram_sessions_schema.sql      # Sesiones conversacionales
│   │   ├── 004_conversation_flow_tracking.sql    # Historial de transiciones por etapa
│   │   └── 005_telegram_message_history.sql      # Historial de mensajes por chat
│   └── sops/
│       ├── 02_supabase_model.md                  # Modelo de datos Supabase
│       └── 07_payload_contracts_v1.md            # Contratos de payload entre servicios
└── CLAUDE.md
```

## Integraciones activas

| Servicio | Tipo | Estado | Archivo de servicio |
|----------|------|--------|---------------------|
| Supabase | Base de datos | Activo | `1-agente/app/services/supabase_service.py` |
| OpenAI | IA conversacional | Activo | `1-agente/app/services/openai_service.py` |
| Telegram | Mensajeria | Activo | `1-agente/app/services/telegram_service.py` |
| LiveConnect | Conversaciones | Webhook activo | `main.py /webhooks/liveconnect` |
| Anarvet | Resultados lab | Webhook activo | `main.py /webhooks/anarvet/result` |
| WhatsApp Business | Mensajeria | Pendiente V2 | - |
| Alegra | Contabilidad | Pendiente | - |

## Webhooks entrantes

| Endpoint | Secret Header | Descripcion |
|----------|---------------|-------------|
| `POST /webhooks/telegram` | `X-Telegram-Bot-Api-Secret-Token` | Updates de Telegram |
| `POST /webhooks/liveconnect` | `X-LiveConnect-Secret` | Conversaciones LiveConnect |
| `POST /webhooks/anarvet/result` | `X-Anarvet-Secret` | Resultados de laboratorio |

## Reglas
- Todo cambio en la BD se documenta PRIMERO en un nuevo archivo SQL aqui
- Los SQL schemas se numeran secuencialmente (004_, 005_, etc.)
- Los contratos de API se documentan en SOPs antes de implementar
- No modificar tablas existentes sin crear un ADR en `docs/decisions/`
- Los servicios (clientes API) viven en `1-agente/app/services/` pero se documentan aqui
