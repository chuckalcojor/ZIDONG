# SOP 08 - Dashboard Ops Center (V1)

## Goal
Provide a single operational console for laboratory staff with secure access and actionable metrics.

## Access Model
- Private login only (`/login`).
- Credentials from environment variables.
- Session-based protection for all dashboard endpoints.

## Core Sections
1. Funnel operativo (received -> assigned -> on_route -> in_lab -> processed -> sent).
2. Clientes y mensajero asignado (coverage + gaps).
3. Edicion inline de perfil comercial/facturacion (campos Si/No y catalogos).
4. Conversaciones LiveConnect (estado, resumen, ultimos mensajes).
5. Seguimiento de solicitudes y muestras.
6. Catalogo de analisis y valores.

## Operational KPIs
- Total clients.
- Clients without assigned courier.
- Active requests.
- Samples pending pickup.
- Samples in analysis.
- Results ready for delivery.
- Open conversations.

## Reliability Rules
- If integration tables are unavailable, dashboard should still load with partial data.
- All operational state transitions must be persisted in event tables.
- No hidden assignment logic outside deterministic rules.
