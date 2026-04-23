# ADR 009 - Secuencia de validacion de cliente por NIT/NID y nombre

## Status
Accepted

## Context
En el flujo de `programacion_rutas` se detectaron fallas en identificacion de clientes:

- busqueda estricta por NIT/NID no toleraba formatos con o sin digito de verificacion,
- busqueda por nombre no toleraba variaciones razonables,
- el bot podia repetir la misma solicitud de dato (NIT o nombre) tras un fallo,
- no existia un fallback operativo claro cuando fallaban NIT y nombre.

## Decision
Se implementan guardas deterministicas de identificacion con secuencia obligatoria:

1. Validar por NIT/NID con matching tolerante (formatos con/sin guion y con/sin DV).
2. Si no se encuentra por NIT/NID, pedir nombre de veterinaria (sin volver a pedir NIT en ese paso).
3. Si tampoco se encuentra por nombre, escalar a humano con mensaje explicito de atencion al cliente.

Adicionalmente:

- Se mejora matching por nombre con normalizacion + similitud (tokens y distancia de cadena).
- Se persiste estado de intentos por tipo de dato en `captured_fields` para evitar preguntas repetidas.
- Se conserva fallback por indice de conocimiento cuando aplica para continuidad operativa.

## Consequences
Positivas:

- Menos loops en validacion de cliente.
- Mayor tasa de match para NIT/NID y nombres con variaciones comunes.
- Escalado humano consistente cuando no hay match en ambas vias.

Costos:

- Mayor complejidad de reglas de identificacion.
- Requiere mantener pruebas de regresion de la secuencia NIT -> nombre -> handoff.

## Verification
- Pruebas agregadas y ajustadas en `tests/test_conversation_flow.py`.
- Validacion ejecutada con:
  - `py -m unittest tests.test_conversation_flow`
  - `py -m unittest discover -s tests -p "test_*.py"`
