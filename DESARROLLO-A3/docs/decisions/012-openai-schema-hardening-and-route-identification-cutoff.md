# ADR 012 - Endurecimiento de schema OpenAI y corte de loop por NIT repetido

## Status
Accepted

## Context
En pruebas de produccion y regresion se detectaron dos fallas recurrentes:

1. Errores `invalid_json_schema` en OpenAI Responses API por schema no compatible en `captured_fields`.
2. Loop conversacional en ruta cuando el usuario repetia el mismo NIT no encontrado.

La primera falla activaba `openai_fallback` y luego `openai_circuit_active`, degradando calidad y consistencia de respuestas.

## Decision
Se aplican guardas permanentes en backend:

1. Ajustar schema estricto de `captured_fields` para cumplir Responses API:
   - `additionalProperties=false`
   - `required` con todas las llaves definidas en `properties`.
2. Aumentar resiliencia de llamada OpenAI con timeout mayor y 1 reintento.
3. Forzar fallback util cuando la configuracion repite modelo primario:
   - si `OPENAI_FALLBACK_MODEL` coincide con `OPENAI_MODEL`, agregar `gpt-4.1-mini` como backup automatico.
4. Cortar loop de identificacion en ruta:
   - si el mismo NIT no encontrado se repite 3 veces, escalar a atencion humana (`operaciones`).

## Consequences
Positivas:

- Se elimina el error de schema que disparaba fallback sistematico.
- Se reduce riesgo de circuit breaker por fallas evitables de formato.
- El flujo de ruta deja de ciclar con el mismo NIT invalido.
- El sistema conserva degradacion controlada ante latencia/transitorios de red.

Costos:

- Mayor rigidez del contrato JSON en `generate_turn`.
- Ligero aumento de latencia maxima por timeout/reintento.

## Verification
- Tests actualizados y nuevos en:
  - `DESARROLLO-A3/1-agente-conversacional/tests/test_openai_service.py`
  - `DESARROLLO-A3/1-agente-conversacional/tests/test_conversation_flow.py`
- Suite completa:
  - `py -m unittest discover -s tests -q`
- Benchmark conversacional real (muestra reducida):
  - `py tools/evaluate_gpt5_conversation.py --areas all --single-turn-samples 4 --multiturn-samples 2 --progress-every 10`
