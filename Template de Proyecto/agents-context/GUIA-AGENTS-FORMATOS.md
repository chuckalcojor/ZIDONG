# Guia AGENTS.md y formatos equivalentes

## Que es y por que sirve

`AGENTS.md` es un archivo Markdown en la raiz del repositorio que define contexto operativo para agentes de codigo:

- Como levantar el proyecto
- Como validar cambios (test/lint/build)
- Reglas de estilo
- Reglas de seguridad
- Flujo de commits y PR

Piensalo como un `README` para IA: mas tecnico, mas ejecutable, menos marketing.

## Como funciona en la practica

1. El agente lee instrucciones del archivo de contexto.
2. Ejecuta comandos y cambios siguiendo esas reglas.
3. Si hay conflicto, el prompt del usuario normalmente tiene mayor prioridad.
4. En monorepos, suele aplicar el archivo mas cercano al codigo editado.

## Formatos/nombres comunes por herramienta

No hay un estandar obligatorio global. `AGENTS.md` es abierto y simple. Algunas herramientas usan nombres alternativos por convencion.

- `AGENTS.md` (recomendado como canonico)
- `CLAUDE.md`
- `GEMINI.md`
- `COPILOT.md`
- `CURSOR.md`
- `CODEX.md` o instrucciones via config del entorno
- `AGENT.md` (variante historica en algunos repos)

Recomendacion: usa **siempre** `AGENTS.md` como fuente principal y genera aliases/adaptadores para herramientas concretas.

### Mapa rapido de archivos por tool (practica comun)

- Claude Code: `AGENTS.md` o `CLAUDE.md`
- Gemini CLI: `AGENTS.md` o `GEMINI.md`
- Codex/OpenCode y compatibles: `AGENTS.md`
- Cursor/Copilot/otros IDE agents: suelen aceptar `AGENTS.md` o archivo especifico por convencion del equipo

Nota: el soporte exacto depende de la version de cada herramienta. Si una tool exige nombre especifico, usa adapter.

## Estructura recomendada de AGENTS.md

```markdown
# AGENTS.md

## Resumen del proyecto
- Objetivo del sistema
- Stack principal

## Comandos de desarrollo
- Instalar dependencias
- Ejecutar entorno local
- Ejecutar test/lint/typecheck

## Convenciones de codigo
- Estilo
- Arquitectura
- Patrones permitidos/no permitidos

## Calidad y validacion
- Que checks deben pasar antes de cerrar una tarea
- Politica minima de tests

## Seguridad y datos
- Secretos y variables de entorno
- Datos sensibles
- Acciones prohibidas

## Flujo de contribucion
- Convencion de commits
- Reglas de PR
```

## Estrategia recomendada (canonico + adaptadores)

1. Mantener `AGENTS.md` como unico documento fuente.
2. Crear `CLAUDE.md`, `GEMINI.md`, etc. como wrappers sincronizados.
3. Al actualizar politicas, editar primero `AGENTS.md`.
4. Regenerar o actualizar wrappers en la misma PR/commit.

## Wrapper minimo por herramienta

Ejemplo para `CLAUDE.md` o `GEMINI.md`:

```markdown
# CLAUDE.md

Este proyecto usa AGENTS.md como contexto principal.

Lee y aplica: ./AGENTS.md

Si hay conflicto entre este archivo y AGENTS.md, prevalece AGENTS.md.
```

## Configuracion rapida en herramientas que permiten custom file

- Aider (`.aider.conf.yml`):

```yaml
read: AGENTS.md
```

- Gemini CLI (`.gemini/settings.json`):

```json
{ "contextFileName": "AGENTS.md" }
```

## Migracion desde AGENT.md

Si tienes `AGENT.md` historico, puedes migrar a `AGENTS.md` y dejar compatibilidad:

```bash
mv AGENT.md AGENTS.md && ln -s AGENTS.md AGENT.md
```

## Plantilla rapida para copiar

Usa `templates/AGENTS.template.md` y rellena placeholders como `<PROJECT_NAME>`.

## Skill para automatizar

Usa `skill/SKILL.md` para que un agente:

- Genere `AGENTS.md` desde una plantilla
- Cree wrappers `CLAUDE.md`/`GEMINI.md`/otros
- Valide coherencia entre formatos
- Proponga actualizaciones cuando cambie el flujo tecnico

## Notas importantes

- `AGENTS.md` no reemplaza `README.md`; lo complementa.
- Evita texto ambiguo: escribe instrucciones accionables y verificables.
- Incluye comandos exactos que el agente pueda ejecutar.
