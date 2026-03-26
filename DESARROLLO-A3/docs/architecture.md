# Arquitectura - LABERIT A3 VETERINARIA

## Vision general

Sistema integral para A3 Laboratorio Veterinario (Colombia) que automatiza la recepcion de solicitudes, asignacion de mensajeros, seguimiento de muestras y entrega de resultados.

```
[Cliente Veterinaria]
        |
        v
[Telegram / WhatsApp] ──> [Agente Conversacional (Flask + OpenAI)]
        |                          |
        |                    [Logica de negocio]
        |                    - Clasificacion de intent
        |                    - Asignacion de mensajero
        |                    - Programacion de rutas
        |                          |
        v                          v
[Dashboard Operativo] <──> [Supabase (PostgreSQL)]
        |                          ^
        |                          |
        v                          |
[Equipo A3]               [Integraciones externas]
                           - Anarvet (LIS/resultados)
                           - LiveConnect (conversaciones)
                           - Alegra (contabilidad)
```

## Componentes principales

### 1. Agente Conversacional (`DESARROLLO-A3/1-agente-conversacional/`)

- **Responsabilidad**: Recibir mensajes de clientes, clasificar intents, ejecutar flujos conversacionales, crear solicitudes
- **Patron**: Flask app monolitica con webhook Telegram
- **IA**: OpenAI API (gpt-4.1-mini) con system prompt especializado
- **Flujo conversacional**:
  1. Fase 1: Clasificacion (intent + service_area)
  2. Fase 2: Recogida de datos (campos faltantes)
  3. Fase 3: Confirmacion y ejecucion
  4. Fase 4: Handoff humano si necesario

### 2. Plataforma/Dashboard (`DESARROLLO-A3/2-plataforma/`)

- **Responsabilidad**: Panel operativo para el equipo de A3
- **Estado actual**: Templates HTML + CSS servidos por Flask (dentro del agente)
- **Futuro**: Frontend separado en Next.js + React + Tailwind
- **Vistas**: Dashboard general, Clientes, Muestras, Analisis
- **Autenticacion**: Login basico con usuario/password en env vars

### 3. Conexiones (`DESARROLLO-A3/3-conexiones/`)

- **Responsabilidad**: Integraciones con servicios externos y modelo de datos
- **Base de datos**: Supabase (PostgreSQL) con RLS
- **Webhooks entrantes**: Telegram, LiveConnect, Anarvet
- **Servicios**: OpenAI (IA), Supabase (datos), Telegram (mensajeria)

## Flujo de datos

1. Mensaje llega via webhook Telegram → `POST /webhooks/telegram`
2. Se extrae chat_id y texto → `process_telegram_update()`
3. Se busca cliente por telefono en Supabase
4. Se genera respuesta con OpenAI (flujo conversacional por fases)
5. Se crea request en Supabase con eventos
6. Se gestiona sesion de Telegram (upsert)
7. Se responde al usuario via Telegram API
8. Dashboard lee datos de Supabase para mostrar metricas

## Modelo de datos (tablas principales)

- `clients` - Clinicas veterinarias
- `couriers` - Mensajeros
- `client_courier_assignment` - Asignacion mensajero-cliente
- `requests` - Solicitudes de servicio
- `request_events` - Eventos de cada solicitud
- `lab_samples` - Muestras de laboratorio
- `lab_sample_events` - Eventos de muestras
- `catalog_tests` - Catalogo de analisis disponibles
- `telegram_sessions` - Estado conversacional por chat
- `conversation_stage_events` - Historial de transiciones de etapa conversacional
- `liveconnect_conversations` / `liveconnect_messages` - Datos de LiveConnect

## Decisiones de arquitectura

Ver [decisions/](decisions/) para el registro completo de ADRs.
