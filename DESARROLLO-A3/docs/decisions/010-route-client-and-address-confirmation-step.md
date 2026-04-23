# ADR 010 - Confirmacion explicita de cliente y direccion en programacion de recogida

## Status
Accepted

## Context
Durante la programacion de recogida, cuando el cliente ya existia en base, el flujo confirmaba direccion de forma operativa, pero sin un paso explicito de validacion de identidad del cliente detectado.

Esto generaba riesgo de:

- programar con cliente equivocado cuando el usuario respondia "no" por mismatch de cliente,
- pasar de correccion de direccion a programacion final sin reconfirmacion clara,
- respuestas ambiguas sobre si se habia validado correctamente cliente + direccion.

## Decision
Se agrega un comportamiento explicito en ruta para clientes existentes:

1. Mensaje de confirmacion con cliente detectado y direccion detectada.
2. Pregunta directa: confirmar cliente correcto y direccion correcta.
3. Si responde negativo por direccion: solicitar direccion actualizada y volver a confirmar antes de programar.
4. Si responde negativo por cliente incorrecto: limpiar cliente detectado y regresar a identificacion por NIF/NIT o nombre fiscal.

## Consequences
Positivas:

- Menor riesgo operativo de programar para cliente equivocado.
- Mayor claridad para el usuario sobre lo detectado en sistema.
- Correcciones de direccion con reconfirmacion previa a programacion.

Costos:

- Un turno adicional en escenarios de correccion.
- Mayor complejidad de guardas en el flujo de ruta.

## Verification
- Nuevas pruebas de regresion en `tests/test_conversation_flow.py` para:
  - confirmacion explicita cliente + direccion,
  - mismatch de cliente y regreso a identificacion,
  - reconfirmacion tras direccion corregida.
- Validacion ejecutada con:
  - `py -m unittest tests.test_conversation_flow`
  - `py -m unittest discover -s tests -p "test_*.py"`
