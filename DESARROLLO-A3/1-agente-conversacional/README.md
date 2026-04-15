# LAB Veterinaria - V1

Backend V1 para intake por Telegram + Supabase y dashboard operativo privado.

## Stack
- Flask
- Supabase (REST)
- Telegram Bot API
- OpenPyXL (importacion Excel)
- PyPDF (importacion catalogo PDF)

## Setup

1. Copiar `.env.example` a `.env` y completar valores.
2. Instalar dependencias:

```bash
py -m pip install -r requirements.txt
```

3. Aplicar SQL en Supabase:
- Ejecutar `architecture/sql/001_v1_core_schema.sql` en SQL Editor.
- Ejecutar `architecture/sql/002_dashboard_operational_schema.sql` en SQL Editor.
- Ejecutar `architecture/sql/003_telegram_sessions_schema.sql` en SQL Editor.
- Ejecutar `architecture/sql/004_conversation_flow_tracking.sql` en SQL Editor.
- Ejecutar `architecture/sql/005_telegram_message_history.sql` en SQL Editor.
- Ejecutar `../3-conexiones/architecture/sql/006_clients_a3_knowledge_index.sql` en SQL Editor.
- Ejecutar `../3-conexiones/architecture/sql/007_clients_dashboard_profile_fields.sql` en SQL Editor.

4. Importar datos iniciales:

```bash
py tools/import_clients_excel.py
py tools/import_catalog_pdf.py
py tools/import_route_assignments_excel.py --excel "C:\Users\gasto\Downloads\A3 VETERINARIA.xlsx"
```

5. Levantar API local:

```bash
py -m app.main
```

5.1 Verificar conexiones (Telegram + Supabase):

```bash
py tools/link_check.py
```

6. Configurar webhook Telegram (cuando tengas URL publica):

```bash
set TELEGRAM_BOT_TOKEN=...
set TELEGRAM_WEBHOOK_SECRET=...
set TELEGRAM_WEBHOOK_URL=https://tu-dominio.com/webhooks/telegram
py tools/set_telegram_webhook.py
```

6.1 Desarrollo local con localhost (webhook en tiempo real):

Terminal A:

```bash
py -m app.main
```

Terminal B:

```bash
py tools/dev_localtunnel_webhook.py --port 8000
```

Este script:
- levanta un tunel publico temporal hacia `localhost:8000`,
- configura `setWebhook` automaticamente,
- guarda `TELEGRAM_WEBHOOK_URL` en `.env`.

Mantener ambas terminales abiertas durante la prueba.

6.2 Nota operativa:

El bot opera unicamente en modo webhook para minimizar latencia y simplificar operacion.

## Endpoint
- `POST /webhooks/telegram`
  - Valida header `X-Telegram-Bot-Api-Secret-Token`.
  - Rutea mensaje a: `route_scheduling`, `accounting`, `results`, `new_client`, `unknown`.
  - Guarda `requests` y `request_events` en Supabase.
  - Ejecuta asignacion fija por cliente en `route_scheduling`.
- `POST /webhooks/liveconnect`
  - Ingesta conversaciones y mensajes para trazabilidad de atencion.
  - Header opcional: `X-LiveConnect-Secret`.
- `POST /webhooks/anarvet/result`
  - Sincroniza estado de muestra/resultados hacia `lab_samples`.
  - Header opcional: `X-Anarvet-Secret`.
- `POST /webhooks/new-client-registration`
  - Recibe altas de cliente nuevo desde Google Forms (o integrador intermedio).
  - Header opcional/recomendado: `X-New-Client-Secret`.
  - Upsert en `clients_a3_knowledge` y `clients_a3_professionals`.
  - Inserta/actualiza en `clients` cuando llega direccion.

### Payload esperado (JSON)

Puedes enviar los campos como claves directas o dentro de `responses`:

```json
{
  "responses": {
    "Nombre de la veterinaria o medico veterinario": "Clinica Vet Norte",
    "Direccion y ubicacion en Google Maps": "Cra 12 # 34-56",
    "Barrio y Localidad": "Kennedy",
    "N Celular": "3001234567",
    "Email": "vetnorte@example.com",
    "Medico Veterinario": "Dra Paula Rios",
    "N Tarjeta Profesional": "TP-9988",
    "Rut": "900123456"
  }
}
```

Integracion sugerida para Google Forms:
- Trigger `onFormSubmit` en Google Apps Script.
- Enviar POST JSON al endpoint `/webhooks/new-client-registration`.
- Incluir header `X-New-Client-Secret` con `NEW_CLIENT_FORM_WEBHOOK_SECRET`.

## Automatizacion de programacion de ruta (sandbox)

- Cuando el flujo de ruta llega a confirmacion final, el backend registra automaticamente un evento
  `route_form_mock_submitted` en `request_events` con estructura equivalente al formulario operativo.
- En el mismo punto, intenta asignar mensajero con `client_courier_assignment` y registra
  `assignment_result` en `request_events`.
- Este modo no escribe en el Google Form real; sirve para pruebas funcionales sobre la base actual.

## Dashboard privado
- `GET /login`
- `GET /dashboard`
- `GET /clientes`
- `GET /muestras`
- `GET /analisis`
- `GET /flujo`
- `GET /api/dashboard/overview`

Credenciales por `.env`:
- `DASHBOARD_ADMIN_USER`
- `DASHBOARD_ADMIN_PASSWORD`

## Integraciones pendientes (siguiente fase)
- Ingesta automatica desde LiveConnect (`liveconnect_conversations`, `liveconnect_messages`).
- Sincronizacion de resultados desde Anarvet hacia `lab_samples`.

## Orden recomendado de ejecucion
1. Ejecutar SQL `001` y `002`.
2. Correr `py tools/import_clients_excel.py`.
3. Correr `py tools/import_catalog_pdf.py`.
4. Levantar backend y abrir `/login`.
5. Conectar webhooks de Telegram/LiveConnect/Anarvet.

## Datos que debes pasarme para conectar todo
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- URL publica para webhook (dominio o tunnel)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- Dump/base inicial de `clients`, `couriers`, `client_courier_assignment`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (opcional, por defecto `gpt-4.1-mini`)
