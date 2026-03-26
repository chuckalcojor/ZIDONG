# Instrucciones para Claude (Claude Code / Claude Chat)

## Canonico

- Archivo canonico del repositorio: `AGENTS.md` (raiz)
- Este archivo es adaptador para Claude
- Si hay conflicto entre archivos de contexto, prevalece `AGENTS.md`

## Como usar este proyecto con Claude

### Claude Code (CLI / VS Code)
1. Leer `AGENTS.md` en la raiz del proyecto (canonico)
2. Claude Code lee automaticamente `CLAUDE.md` como adaptador
3. Las reglas de separacion de zonas estan ahi - respetarlas siempre
4. Skills disponibles en `INTERNO-EQUIPO/herramientas/`
5. Template de estructura de proyecto en `agents-md/claude-code-project-template.md`

### Claude Chat (conversacion)
1. Pegar el contenido de `CONTEXTO-UNIVERSAL.md` al inicio de la conversacion
2. Especificar en que zona vas a trabajar (agente, plataforma, conexiones)
3. Claude no tiene acceso al filesystem - copiar los archivos relevantes

## Comportamiento esperado
- Seguir conventional commits (feat:, fix:, refactor:, docs:)
- Preferir editar archivos existentes sobre crear nuevos
- No tocar configuracion sin confirmar
- Ejecutar tests despues de cambios en codigo
- Documentar decisiones en architecture/sops/ de la seccion correspondiente

## Archivos clave que Claude debe leer

- `CLAUDE.md` (raiz) - Se carga automaticamente por Claude Code
- `DESARROLLO-A3/*/CONTEXTO.md` - Contexto local de cada modulo (universal, no solo Claude)
- `DESARROLLO-A3/1-agente-conversacional/app/main.py` - Punto de entrada del bot
- `DESARROLLO-A3/1-agente-conversacional/app/ai_prompt.py` - System prompt del bot
- `DESARROLLO-A3/3-conexiones/architecture/sql/` - Schemas de la BD

## Skills disponibles

Las 27 skills en `INTERNO-EQUIPO/herramientas/` estan documentadas en CONTEXTO-UNIVERSAL.md. Claude Code puede leer cualquier SKILL.md directamente para aplicar esa skill al trabajo actual.
