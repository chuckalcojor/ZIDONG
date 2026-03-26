# ADR-002: Reestructuracion del proyecto en zonas separadas

## Estado
Aceptado (2026-03-20)

## Contexto
El proyecto mezclaba el codigo del producto (bot + dashboard) con las herramientas internas del equipo de desarrollo (skills de IA, prompts, instrucciones). El equipo trabaja con multiples IAs (Claude, OpenAI, Gemini) y necesita que cualquiera pueda entender el proyecto sin mezclar lo interno con lo entregable.

## Decision
Separar en 4 zonas:
1. `DESARROLLO-A3/` con 3 secciones (agente, plataforma, conexiones)
2. `INTERNO-EQUIPO/` con agents-md/ y herramientas/
3. `Informacion/` (docs de negocio, solo lectura)
4. `REFERENCIAS/` (material visual, solo lectura)

Crear `agents-md/CONTEXTO-UNIVERSAL.md` como punto de entrada para cualquier IA.

## Consecuencias
- Separacion clara entre producto y herramientas internas
- Cualquier IA puede onboardearse leyendo CONTEXTO-UNIVERSAL.md
- Los SOPs se distribuyen por seccion (agente vs plataforma vs conexiones)
- El codigo del bot sigue siendo un monolito Flask hasta que se separe el frontend
