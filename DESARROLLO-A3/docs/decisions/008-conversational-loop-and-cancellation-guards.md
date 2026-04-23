# ADR 008 - Guardas anti-loop y cierre operativo en el agente conversacional

## Status
Accepted

## Context
En pruebas reales de Telegram se detectaron 4 fallas repetitivas:

1. Respuestas duplicadas en consultas de catalogo cuando el usuario hacia follow-up.
2. Repeticion del mensaje "solicitud ya programada" ante "No gracias".
3. Falta de cancelacion explicita en programacion de ruta.
4. Repeticion en contabilidad cuando el usuario solo enviaba identificadores numericos.

Estas fallas degradaban experiencia y causaban loops conversacionales sin salida clara.

## Decision
Se agregan guardas deterministicas en backend (no solo en prompt):

1. Anti-loop por area para respuestas repetidas, con variacion util en `unknown` (catalogo) y `accounting`.
2. Detector de cierre conversacional (`No gracias` y variantes) para cerrar en ruta programada.
3. Detector de cancelacion de ruta para transicionar a estado `cancelled` y registrar evento operativo.
4. Mini-guard de contabilidad para capturar `NIF/NIT` + referencia de factura/periodo y escalar a handoff cuando corresponde.
5. Escalado a `operaciones` tras multiples intentos fallidos de identificacion en ruta.

## Consequences
Positivas:
- Se eliminan loops mas frecuentes observados en produccion.
- El flujo tiene salidas explicitas para cierre, cancelacion y handoff.
- Mayor trazabilidad en `request_events` para casos cancelados.

Costos:
- Mayor complejidad de reglas en `app/main.py`.
- Requiere mantener tests de regresion sobre conversaciones reales.

## Verification
- Nuevos tests en `DESARROLLO-A3/1-agente-conversacional/tests/test_conversation_flow.py`.
- Suite completa ejecutada con `py -m unittest discover -s tests -p "test_*.py"`.
