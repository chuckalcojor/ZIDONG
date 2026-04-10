# ADR 004 - Modo Mock para dashboard

## Estado
Aprobado

## Contexto
Se requiere avanzar en rediseno visual y pruebas funcionales del dashboard sin depender de la disponibilidad de Supabase o integraciones externas.

## Decision
Se agrega un selector de fuente de datos para dashboard controlado por variable de entorno:

- `DASHBOARD_DATA_MODE=mock`: carga datos falsos desde `DESARROLLO-A3/2-plataforma/mock-data/dashboard_context.json`.
- `DASHBOARD_DATA_MODE=real`: usa el flujo real existente contra Supabase.

La carpeta `DESARROLLO-A3/2-plataforma/mock-data/` queda aislada y puede eliminarse sin afectar el flujo real.

## Consecuencias

### Positivas
- Permite demos y pruebas de UX sin backend real.
- Facilita testeo de todas las vistas (`/dashboard`, `/clientes`, `/muestras`, `/analisis`, `/flujo`) con datos consistentes.
- El rollback es inmediato con cambio de variable.

### Riesgos
- Posible confusion entre datos reales y mock si no se documenta el modo activo.

## Mitigaciones
- Documentacion explicita en `mock-data/README.md` y `1-agente-conversacional/README.md`.
- Default local actual configurado en `mock` hasta nuevo aviso.
