# Instrucciones para OpenAI (ChatGPT / GPT API / Codex)

## Canonico y modelo de trabajo

- Archivo canonico del repositorio: `AGENTS.md` (raiz)
- Este archivo es adaptador para OpenAI/Codex
- Modelo principal de ejecucion del equipo: ChatGPT 5.3 Codex (OpenCode)
- Si hay conflicto entre archivos de contexto, prevalece `AGENTS.md`

## Como usar este proyecto con OpenAI

### ChatGPT / GPT-4
1. Leer `AGENTS.md` en la raiz (fuente canonica)
2. Pegar el contenido de `CONTEXTO-UNIVERSAL.md` al inicio de la conversacion
3. Especificar en que zona vas a trabajar (agente, plataforma, conexiones)
4. Para cambios en la BD, copiar los SQL schemas de `DESARROLLO-A3/3-conexiones/architecture/sql/`
5. Para cambios en el bot, copiar `app/main.py` y los SOPs relevantes

### Custom GPTs
1. Incluir `CONTEXTO-UNIVERSAL.md` como instruccion del sistema
2. Subir los archivos de la zona en la que se va a trabajar
3. Configurar el knowledge base con los SOPs de architecture/

### API (para el producto)
- El bot usa OpenAI API con modelo gpt-4.1-mini
- El system prompt esta en `DESARROLLO-A3/1-agente-conversacional/app/ai_prompt.py`
- La config de API esta en `DESARROLLO-A3/1-agente-conversacional/app/services/openai_service.py`
- IMPORTANTE: esto es la IA DEL PRODUCTO, no la IA del equipo

## Archivos clave que GPT debe leer

- `CONTEXTO-UNIVERSAL.md` - Punto de entrada (pegarlo al inicio de la conversacion)
- `DESARROLLO-A3/*/CONTEXTO.md` - Contexto local de cada modulo (universal, no solo Claude)
- `DESARROLLO-A3/1-agente-conversacional/app/main.py` - Punto de entrada del bot
- `DESARROLLO-A3/1-agente-conversacional/app/ai_prompt.py` - System prompt del bot
- `DESARROLLO-A3/3-conexiones/architecture/sql/` - Schemas de la BD

## Skills disponibles

Las 27 skills en `INTERNO-EQUIPO/herramientas/` estan documentadas en CONTEXTO-UNIVERSAL.md. Para usar una skill, pegar el contenido de su SKILL.md en la conversacion.

## Reglas

- Respetar la separacion de zonas (ver CONTEXTO-UNIVERSAL.md)
- No mezclar instrucciones internas con el codigo del producto
- El system prompt del bot (ai_prompt.py) es parte de DESARROLLO-A3, no de INTERNO-EQUIPO
