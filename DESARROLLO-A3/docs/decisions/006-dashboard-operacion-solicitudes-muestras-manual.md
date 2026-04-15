# ADR-006: Gestion operativa manual de solicitudes y muestras en dashboard

## Estado
Aceptado (2026-04-15)

## Contexto
Operaciones necesitaba una vista dedicada para gestionar solicitudes de retiro con campos de domicilio, cantidad de muestras y tipo de muestra.

Adicionalmente se requeria actualizacion manual de estados para solicitudes y muestras desde el dashboard, manteniendo trazabilidad y coherencia con las demas pestañas.

## Decision
- Agregar pestaña `Solicitudes` en el dashboard con datos operativos vinculados:
  - cliente,
  - domicilio,
  - cantidad de muestras por solicitud,
  - tipos de muestra,
  - mensajero,
  - estado editable.
- Exponer endpoint autenticado `POST /api/dashboard/request-status` para actualizar `requests.status`.
- Exponer endpoint autenticado `POST /api/dashboard/sample-status` para actualizar `lab_samples.status`.
- Registrar cada cambio manual en eventos para auditoria:
  - `request_events` con `event_type=dashboard_status_update`,
  - `lab_sample_events` con `event_type=dashboard_status_update`.
- Mantener un unico origen de datos para todas las pestañas (`build_dashboard_context`) para asegurar coherencia entre `Tablero`, `Solicitudes`, `Clientes`, `Muestras` y `Analisis`.

## Consecuencias
- Operaciones puede gestionar estados manualmente sin salir del dashboard.
- Los cambios de estado impactan de forma consistente los KPIs y tablas relacionadas tras recarga.
- Se mejora trazabilidad historica de cambios sin alterar integraciones de webhook existentes.
