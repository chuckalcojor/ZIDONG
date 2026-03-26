# Modulo: Agente Conversacional

## Responsabilidad
Bot que atiende a los clientes de A3 Laboratorio Veterinario por Telegram (y futuro WhatsApp). Clasifica intents, recoge datos, asigna mensajeros, programa rutas y escala a humanos cuando es necesario.

## Estructura

```
1-agente-conversacional/
├── app/
│   ├── main.py              # Punto de entrada Flask, rutas, webhook handlers
│   ├── logic.py              # Logica pura: routing, schedule, assignment
│   ├── ai_prompt.py          # System prompt para OpenAI
│   ├── config.py             # Settings desde env vars
│   ├── __init__.py
│   ├── services/
│   │   ├── openai_service.py    # Cliente OpenAI API
│   │   ├── supabase_service.py  # Cliente Supabase REST
│   │   └── telegram_service.py  # Cliente Telegram Bot API
│   ├── templates/
│   │   ├── dashboard.html    # Dashboard operativo (HTML)
│   │   └── login.html        # Login del dashboard
│   └── static/
│       └── app.css           # Estilos del dashboard
├── tools/                    # Scripts operativos
│   ├── assignment_engine.py
│   ├── import_catalog_pdf.py
│   ├── import_clients_excel.py
│   ├── intake_router.py
│   ├── dev_localtunnel_webhook.py
│   ├── schedule_business_day.py
│   ├── set_telegram_webhook.py
│   └── link_check.py
├── architecture/sops/        # SOPs del agente
├── .env / .env.example
└── requirements.txt
```

## Convenciones
- Un servicio por archivo en `app/services/`
- La logica pura (sin I/O) va en `logic.py`
- Los prompts de IA van en `ai_prompt.py`, no hardcodeados en main
- Las settings se leen de env vars via `config.py`
- Los scripts operativos van en `tools/`, no en `app/`

## Dependencias
- Flask (web framework)
- httpx (HTTP client para APIs externas)
- python-dotenv (env vars)
- OpenAI API (via servicio en app/services/)
- Supabase (via servicio en app/services/)
- Telegram Bot API (via servicio en app/services/)

## Flujo principal
1. Webhook recibe update → `telegram_webhook()`
2. Se extrae chat_id y texto → `process_telegram_update()`
3. Si hay OpenAI configurado → flujo IA (generate_turn con fases)
4. Si no → flujo legacy (routing por keywords)
5. Se crea request + eventos en Supabase
6. Se responde al usuario via Telegram

## Reglas
- No modificar `ai_prompt.py` sin revisar el SOP 03_conversation_telegram_v1
- No cambiar el modelo de datos sin actualizar `3-conexiones/`
- Los templates de dashboard pertenecen logicamente a `2-plataforma/` aunque vivan aqui temporalmente
- Nunca hardcodear tokens o secrets
