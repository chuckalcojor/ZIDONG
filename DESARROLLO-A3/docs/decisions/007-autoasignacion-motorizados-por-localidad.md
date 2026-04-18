# ADR-007: Autoasignacion de motorizados por localidad para clientes nuevos

## Estado
Aceptado (2026-04-18)

## Contexto
La operacion de A3 requiere asignar motorizado de forma automatica al registrar clientes nuevos en Bogota.

Hasta ahora la asignacion estaba centrada en ajustes manuales por cliente. Esto genera friccion operativa y tiempos extra cuando el volumen de registros aumenta.

Adicionalmente, el cliente pidio una vista dedicada de `Motorizados` para administrar cobertura territorial y visualizarla en mapa.

## Decision
- Definir regla operativa inicial: `1 localidad = 1 motorizado`.
- Aplicar autoasignacion solo a clientes nuevos recibidos en `POST /webhooks/new-client-registration`.
- Crear tabla `courier_locality_coverage` como fuente de verdad para cobertura por localidad.
- Mantener catalogo cerrado de localidades de Bogota en backend para validar entradas y evitar variaciones de texto libre.
- Si una localidad no tiene cobertura configurada, el cliente queda sin asignar (sin fallback automatico a motorizado comodin).
- Incorporar vista `Motorizados` en dashboard con:
  - listado de motorizados activos,
  - configuracion de cobertura por localidad,
  - mapa operativo por localidad con colores por motorizado.

## Consecuencias
- Se reduce trabajo manual en onboarding de clientes nuevos.
- El comportamiento de asignacion es deterministico, trazable y facil de auditar.
- Se evita asignar incorrectamente cuando falta cobertura (prioridad a seguridad operativa).
- Queda preparado el camino para fases futuras: balanceo multi-motorizado por localidad y optimizacion de rutas.
