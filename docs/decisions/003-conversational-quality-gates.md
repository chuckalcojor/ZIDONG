# ADR 003 - Conversational Quality Gates for Agent A3

## Status
Accepted

## Context
El agente necesita mejorar naturalidad y robustez sin perder control operativo de las areas core (rutas, resultados, contabilidad y alta de cliente).

Las mejoras de prompt por si solas no son suficientes porque no garantizan regresion controlada ni medicion objetiva de calidad.

## Decision
Se adopta un enfoque incremental basado en quality gates con evaluacion automatizada:

1. Mantener benchmark de clasificacion single-turn y multi-turn.
2. Agregar quality-suite con 5 dimensiones medibles:
   - comprehension
   - coherence
   - naturality
   - utility
   - safety
3. Mantener guardas de precision para evitar desvio de intencion:
   - consultas operativas de ruta no deben caer en catalogo
   - consultas de catalogo deben responder con muestra/toma/valor/tiempo cuando aplique
   - mensajes ambiguos deben pedir aclaracion concreta

## Consequences
Positivas:
- Mejora continua con evidencia numerica.
- Menor riesgo de respuestas ilogicas o fuera de contexto.
- Permite priorizar iteraciones por metricas y no por percepcion.

Costos:
- Mayor mantenimiento del set de prompts y reglas de scoring.
- Ajustes periodicos cuando cambie el comportamiento del modelo.

## Implementation Notes
- Script de evaluacion extendido: `DESARROLLO-A3/1-agente-conversacional/tools/evaluate_gpt5_conversation.py`.
- Reportes en `.tmp/evaluations/` (JSON + Markdown).
- Las metricas de quality-suite se usan para decidir siguientes sprints de mejora conversacional.
