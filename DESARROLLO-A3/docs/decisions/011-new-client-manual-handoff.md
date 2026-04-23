# ADR 011 - Derivacion manual para cliente nuevo en canal conversacional

## Status
Accepted

## Context
El cliente operativo definio que los clientes nuevos se registraran manualmente desde plataforma interna y no por formulario automatico en el bot.

El flujo anterior de `alta_cliente` seguia pidiendo formulario y podia reabrir rutas operativas como si el cliente ya estuviera registrado.

## Decision
Para cualquier deteccion de `new_client` o declaracion de "no estoy registrado":

1. El bot deriva a atencion al cliente/recepcion con mensaje unico.
2. El estado de la sesion pasa a `fase_7_escalado` + `status=escalated`.
3. Se marca `requires_handoff=true` y `handoff_area=operaciones`.
4. Se cierra el flujo automatico de alta en chat (sin formulario, sin reintentos de registro automatico).

## Consequences
Positivas:

- Evita que el bot opere como cliente registrado cuando el usuario es nuevo.
- Alinea el canal conversacional con el proceso manual solicitado por operacion.
- Simplifica trazabilidad de handoff humano para casos de alta.

Costos:

- Requiere intervencion humana para cualquier alta de cliente nuevo.
- Se elimina autoservicio de registro desde chat.

## Verification
- Ajustes y regresiones en `tests/test_conversation_flow.py` para `new_client` y "no estoy registrado".
- Suite ejecutada con:
  - `py -m unittest tests.test_conversation_flow`
  - `py -m unittest discover -s tests -p "test_*.py"`
