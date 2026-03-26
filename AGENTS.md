# AGENTS.md - LABERIT A3 VETERINARIA (Canonico)

Este archivo es la fuente principal de contexto para agentes de codigo en este repositorio.

## Modelo operativo actual
- Agente principal de trabajo: ChatGPT 5.3 Codex (OpenCode)
- Soporte multi-IA: Claude, GPT/OpenAI, Gemini
- Regla: `AGENTS.md` es canonico; `CLAUDE.md` y `INTERNO-EQUIPO/agents-md/*.md` son adaptadores por herramienta
- Base metodologica adicional: `Template de Proyecto/templates/reglas.md` y `Template de Proyecto/templates/workflows.md`

## Proyecto
- Plataforma integral para A3 Laboratorio Veterinario (Colombia)
- Incluye bot conversacional, dashboard operativo e integraciones externas

## Stack
- Backend: Python 3.14 + Flask
- Base de datos: Supabase (PostgreSQL)
- IA del producto: OpenAI API (`gpt-4.1-mini`)
- Mensajeria: Telegram Bot API (migracion a WhatsApp planificada)
- Infra: Render + Supabase hosted

## Estructura y separacion de zonas (estricta)
1. `DESARROLLO-A3/` -> Entregable al cliente (producto)
2. `INTERNO-EQUIPO/` -> Herramientas y contexto del equipo (no producto)
3. `Informacion/` -> Solo lectura
4. `REFERENCIAS/` -> Solo lectura

Reglas criticas:
- Nunca mezclar codigo de `DESARROLLO-A3/` con `INTERNO-EQUIPO/`
- Nunca importar modulos de `INTERNO-EQUIPO/` desde codigo de producto
- Nunca modificar `Informacion/` ni `REFERENCIAS/`
- No crear archivos en raiz salvo archivos de configuracion/contexto (este `AGENTS.md` aplica)

## Flujo obligatorio por tarea
1. Leer `INTERNO-EQUIPO/agents-md/CONTEXTO-UNIVERSAL.md`
2. Leer adaptador IA correspondiente:
   - Claude: `INTERNO-EQUIPO/agents-md/claude.md`
   - OpenAI/Codex: `INTERNO-EQUIPO/agents-md/openai.md`
   - Gemini: `INTERNO-EQUIPO/agents-md/gemini.md`
3. Leer contexto del modulo objetivo:
   - `DESARROLLO-A3/1-agente-conversacional/CONTEXTO.md`
   - `DESARROLLO-A3/2-plataforma/CONTEXTO.md`
   - `DESARROLLO-A3/3-conexiones/CONTEXTO.md`
4. Revisar SOPs antes de tocar esa zona
5. Implementar cambios
6. Verificar (tests/checks aplicables)
7. Documentar decisiones relevantes en `DESARROLLO-A3/docs/decisions/`

## Reglas por dominio
- Cambios de base de datos: documentar primero en `DESARROLLO-A3/3-conexiones/`
- Cambios de dashboard: revisar SOPs en `DESARROLLO-A3/2-plataforma/architecture/sops/`
- Cambios del bot: revisar SOPs en `DESARROLLO-A3/1-agente-conversacional/architecture/sops/`

## Convenciones
- Python y SQL: `snake_case`
- Commits: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`)
- Secretos: solo en `.env`, nunca hardcodeados

## Reglas base de trabajo (siempre activas)
- Priorizar simplicidad, legibilidad y cambios minimos con bajo impacto
- Implementar en pasos pequenos y validar despues de cada cambio relevante
- No marcar una tarea como finalizada sin evidencia de verificacion (tests/logs/checks)
- Explicar decisiones tecnicas de forma breve y clara en espanol
- En debugging, buscar causa raiz (sin parches temporales) y verificar el fix
- Mantener nombres claros y consistentes; evitar complejidad innecesaria

## Workflow operativo (siempre activo)
1. Planificar para tareas no triviales (3+ pasos o decisiones de arquitectura)
2. Ejecutar incrementalmente, actualizando progreso por pasos
3. Verificar antes de cerrar (funcional, pruebas y alcance)
4. Si algo se desvia, detener y re-planificar
5. Capturar lecciones y ajustar reglas para evitar repetir errores

## Comandos de trabajo (referencia)
- Ejecutar app desde: `DESARROLLO-A3/1-agente-conversacional/`
- Tests/lint/build: usar los comandos existentes del modulo, no inventar nuevos

## Calidad minima antes de cerrar tarea
- Alcance solicitado cubierto
- Sin violaciones de separacion de zonas
- Sin secretos en codigo
- Validaciones ejecutadas y reportadas de forma concisa
- Supuestos y pendientes explicitados si aplica

## Jerarquia de contexto
1. Instruccion explicita del usuario
2. Este archivo (`AGENTS.md`)
3. Contextos por herramienta (`CLAUDE.md`, `INTERNO-EQUIPO/agents-md/*.md`)
4. Contextos locales de modulo (`DESARROLLO-A3/*/CONTEXTO.md`)

## Nota de sincronizacion
Si una politica cambia, actualizar primero `AGENTS.md` y luego sincronizar:
- `CLAUDE.md`
- `INTERNO-EQUIPO/agents-md/claude.md`
- `INTERNO-EQUIPO/agents-md/openai.md`
- `INTERNO-EQUIPO/agents-md/gemini.md`
