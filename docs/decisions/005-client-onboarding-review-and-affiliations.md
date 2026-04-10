# ADR 005 - Onboarding con aprobacion humana y gestion de afiliaciones

## Estado
Aprobado

## Contexto
El feedback del cliente exige:

- Separar atencion entre cliente nuevo y cliente frecuente desde el primer mensaje.
- Evitar formularios externos en onboarding y capturar datos en chat.
- Validar cliente nuevo con aprobacion humana antes de habilitar informacion sensible.
- Gestionar relacion clinica-medico veterinario desde la plataforma.

## Decision

1. **Onboarding por chat** para cliente nuevo con estado `pending_manual_approval`.
2. **Bandeja de aprobaciones** en plataforma (`/aprobaciones`) con acciones aprobar/rechazar.
3. **Gestion de afiliaciones** clinica-medico (`/afiliaciones`) con alta y desvinculacion.
4. En modo `mock`, las acciones de aprobacion/afiliacion son simuladas para pruebas UX.

## Consecuencias

### Positivas
- Control humano en validaciones sensibles.
- Menor friccion al eliminar dependencia de formularios externos.
- Trazabilidad de decisiones operativas en eventos.
- Capacidad de administrar cambios de afiliacion clinica-profesional.

### Riesgos
- En modo real, la gestion de afiliaciones depende del esquema vigente de Supabase.
- Si faltan tablas/campos, algunas operaciones deben degradar con mensaje controlado.

## Mitigaciones
- Uso de `safe_fetch` y manejo de `HTTPStatusError`.
- Modo `mock` como entorno de pruebas por defecto hasta nuevo aviso.
