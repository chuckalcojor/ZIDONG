# ADR-004: Perfil de cliente editable para dashboard operativo

## Estado
Aceptado (2026-04-14)

## Contexto
La operacion diaria del dashboard requiere gestionar informacion comercial y de facturacion que no estaba modelada en el perfil actual de clientes.

Ademas, el equipo necesita editar campos de seleccion simple (Si/No y catalogos cortos) directamente desde la vista de clientes para reducir tiempo operativo y evitar cambios manuales fuera del sistema.

## Decision
- Extender `clients_a3_knowledge` con campos de perfil comercial/facturacion para dashboard:
  - `client_code`
  - `commercial_name`
  - `client_type`
  - `billing_email`
  - `vat_regime`
  - `electronic_invoicing`
  - `invoicing_rut_url`
  - `registration_timestamp`
  - `registration_date`
  - `registration_time`
  - `observations`
  - `entered_flag`
- Mantener `client_courier_assignment` como fuente de verdad para asignacion de motorizado.
- Habilitar edicion inline en `/clientes` para campos de seleccion y texto con guardado por cambio.
- Exponer endpoints autenticados para actualizar perfil y motorizado sin salir del dashboard.

## Consecuencias
- El dashboard cubre datos clave de cliente nuevo y facturacion en una sola vista.
- La operacion gana velocidad con controles de un clic para valores binarios y catalogos.
- Se incrementa la responsabilidad de validacion en backend para evitar estados invalidos.
