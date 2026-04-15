# ADR-005: Refresh visual del dashboard usando template de referencia

## Estado
Aceptado (2026-04-15)

## Contexto
El cliente solicito alinear la plataforma con una referencia visual oscura de estilo ejecutivo (sidebar, topbar, tarjetas KPI, bloques de analitica y tablas compactas), sin cambiar datos, logica operativa ni contratos de API.

El dashboard sigue alojado de forma temporal en Flask templates dentro del modulo `1-agente-conversacional`, por lo que la intervencion debia limitarse a la capa de presentacion.

## Decision
- Redisenar unicamente la capa visual de:
  - `1-agente-conversacional/app/templates/dashboard.html`
  - `1-agente-conversacional/app/static/app.css`
  - `1-agente-conversacional/app/templates/login.html`
- Mantener intactas rutas, payloads, estructura de datos, validaciones y persistencia.
- Unificar el lenguaje visual en todas las vistas (`/dashboard`, `/clientes`, `/muestras`, `/analisis`, `/flujo`) con el mismo sistema de estilos.
- Ajustar configuracion visual de ApexCharts para integrarse al nuevo tema sin alterar las fuentes de datos.

## Consecuencias
- El dashboard adopta un estilo visual coherente con la referencia solicitada.
- No hay impacto funcional en backend ni en integraciones externas.
- Se conserva la compatibilidad con la futura migracion del frontend a `2-plataforma/` (Next.js + React + Tailwind).
