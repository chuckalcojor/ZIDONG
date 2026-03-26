# Proyecto: LABERIT A3 VETERINARIA

## Nota de orquestacion de contexto (actual)

- Fuente canonica multi-IA: `AGENTS.md` (raiz)
- Este archivo (`CLAUDE.md`) funciona como adaptador para Claude
- Si hay conflicto entre archivos de contexto, prevalece `AGENTS.md`

## Que es
Plataforma integral para A3 Laboratorio Veterinario (Colombia). Incluye un agente conversacional (Telegram/WhatsApp), un dashboard operativo, e integraciones con servicios externos (Supabase, OpenAI, Telegram, LiveConnect, Anarvet).

## Stack
- Backend: Python 3.14 + Flask
- Base de datos: Supabase (PostgreSQL)
- IA: OpenAI API (gpt-4.1-mini)
- Mensajeria: Telegram Bot API
- Infra: Render / Supabase hosted

---

## ESTRUCTURA DEL PROYECTO - REGLAS ESTRICTAS

Este proyecto tiene 4 zonas completamente separadas. NUNCA mezclar codigo, archivos o logica entre zonas.

### ZONA 1: DESARROLLO-A3/ (Entregable al cliente)
Todo lo que se entrega al cliente A3. Se subdivide en 3 secciones:

#### 1-agente-conversacional/
- **Que es**: El bot conversacional que atiende a los clientes de A3 por Telegram/WhatsApp
- **Contiene**: App Flask completa (app/), scripts operativos (tools/), SOPs del agente
- **Codigo fuente**: `app/main.py`, `app/logic.py`, `app/ai_prompt.py`, `app/config.py`
- **Servicios**: `app/services/` (openai, supabase, telegram)
- **Regla**: Este es el nucleo del bot. Los cambios aqui afectan directamente al servicio en produccion

#### 2-plataforma/
- **Que es**: El dashboard operativo y plataforma web de A3
- **Contiene**: Actualmente templates HTML y CSS dentro del agente (app/templates/, app/static/). Los SOPs de dashboard estan aqui
- **SOPs**: 05_dashboard_v1, 08_dashboard_ops_center, 09_integration_payloads_dashboard
- **Futuro**: Cuando se separe el frontend (Next.js/React), el codigo ira aqui
- **Regla**: Los cambios de UI/dashboard se documentan aqui aunque el codigo viva temporalmente en 1-agente-conversacional/app/templates/

#### 3-conexiones/
- **Que es**: Integraciones con servicios externos y esquemas de datos
- **Contiene**: SQL schemas, modelo de datos Supabase, contratos de API
- **SOPs**: 02_supabase_model, 07_payload_contracts_v1
- **SQL**: Schemas de la base de datos (001_core, 002_dashboard, 003_telegram_sessions)
- **Regla**: Cualquier cambio en la base de datos o en contratos de API se documenta aqui PRIMERO

### ZONA 2: INTERNO-EQUIPO/ (Solo para el equipo de desarrollo)
Herramientas internas que usa el equipo para desarrollar. NO es parte del entregable a A3.

#### agents-md/ (Instrucciones por IA)

- **CONTEXTO-UNIVERSAL.md** - Punto de entrada para CUALQUIER IA. Leer siempre primero
- **claude.md** - Instrucciones especificas para Claude (Code y Chat)
- **openai.md** - Instrucciones especificas para GPT/OpenAI
- **gemini.md** - Project Map y estado para Gemini
- **blast-protocol.md** - Metodologia B.L.A.S.T. (compartida entre todas las IAs)
- **claude-code-project-template.md** - Template de estructura de proyecto
- Cuando se trabaje con cualquier IA, cargar primero CONTEXTO-UNIVERSAL.md y luego el archivo especifico de esa IA

#### herramientas/ (Skills de productividad del equipo)

27 skills organizadas por area. NO son funcionalidad del producto. Son herramientas para que el equipo (humanos + IAs) desarrolle mas rapido.

**1-whatsapp-agent/** (9 skills - agentes conversacionales):

- `agent-memory-systems` - Arquitectura de memoria para agentes (short/long term, vector stores)
- `ai-agent-development` - Desarrollo de agentes autonomos (CrewAI, LangGraph, custom)
- `langgraph` - Framework LangGraph para apps multi-actor con estado
- `prompt-engineering-patterns` - Patrones avanzados de prompt engineering
- `rag-engineer` - Sistemas RAG (embeddings, vector DBs, chunking, retrieval)
- `visualization-expert` - Seleccion de graficos y visualizacion de datos
- `automate-whatsapp` - Automatizaciones WhatsApp con Kapso workflows
- `observe-whatsapp` - Debug y troubleshooting de WhatsApp en produccion
- `whatsapp-automation` - Automatizacion WhatsApp Business via Composio

**2-dashboard-plataforma/** (11 skills - dashboard y frontend/backend):

- `api-design-principles` - Diseño de APIs REST y GraphQL
- `fastapi-pro` - APIs async con FastAPI + SQLAlchemy + Pydantic
- `graphql-architect` - GraphQL con federation, caching, real-time
- `nodejs-best-practices` - Principios Node.js y seleccion de framework
- `kpi-dashboard-design` - Diseño de dashboards KPI y metricas
- `nextjs-best-practices` - Next.js App Router y Server Components
- `nextjs-supabase-auth` - Integracion Supabase Auth + Next.js
- `react-best-practices` - Optimizacion de rendimiento React/Next.js
- `react-flow-architect` - Aplicaciones interactivas de grafos con ReactFlow
- `tailwind-design-system` - Design systems con Tailwind CSS
- `ui-ux-pro-max` - Diseño UI/UX completo (estilos, paletas, tipografia, stacks)

**3-multi-agentes-productividad/** (7 skills - orquestacion y productividad):

- `agent-orchestration-multi-agent-optimize` - Optimizar sistemas multi-agente
- `brainstorming` - Transformar ideas vagas en diseños validados
- `dispatching-parallel-agents` - Despachar tareas independientes en paralelo
- `executing-plans` - Ejecutar planes escritos con checkpoints de revision
- `multi-agent-brainstorming` - Peer-review simulado con agentes especializados
- `planning-with-files` - Planificacion file-based (task_plan, findings, progress)
- `subagent-driven-development` - Desarrollo con sub-agentes independientes

### ZONA 3: Informacion/
- Documentos de negocio del cliente: catalogo de productos, relacion de clientes, etapas
- Solo lectura. No modificar estos archivos

### ZONA 4: REFERENCIAS/
- Material visual de referencia (mockups, ejemplos de plataformas)
- Solo lectura

---

## REGLAS CRITICAS - LEER SIEMPRE

### Separacion de codigo
1. **NUNCA** mezclar codigo de DESARROLLO-A3/ con INTERNO-EQUIPO/
2. **NUNCA** importar modulos de INTERNO-EQUIPO/ desde DESARROLLO-A3/
3. **NUNCA** poner skills o instrucciones del equipo dentro del codigo del producto
4. El agente conversacional de INTERNO-EQUIPO/ (Claude Code, skills) es DIFERENTE al agente conversacional de DESARROLLO-A3/ (bot de Telegram para A3)

### Flujo de trabajo
5. Antes de modificar la base de datos, documentar el cambio en `DESARROLLO-A3/3-conexiones/`
6. Antes de modificar el dashboard, revisar SOPs en `DESARROLLO-A3/2-plataforma/`
7. Los cambios en el bot requieren revisar `DESARROLLO-A3/1-agente-conversacional/architecture/sops/`
8. Ejecutar el app desde `DESARROLLO-A3/1-agente-conversacional/` (cd a esa carpeta)

### Convenciones
- Python: snake_case para archivos y variables
- SQL: snake_case para tablas y columnas
- Commits: conventional commits (feat:, fix:, refactor:, docs:)
- Variables de entorno en `.env` (nunca hardcodear secretos)

### Que NO hacer
- No crear archivos en la raiz del proyecto (solo CLAUDE.md y archivos de config)
- No mover codigo entre las 3 secciones de DESARROLLO-A3/ sin justificacion
- No modificar archivos de Informacion/ o REFERENCIAS/
- No incluir __pycache__ o .tmp en commits

---

## ARQUITECTURA Y DOCUMENTACION

### Estructura completa del repositorio

```text
LABERIT A3 VETERINARIA/
├── CLAUDE.md                              # Este archivo - reglas del proyecto
├── .claude/
│   ├── settings.local.json                # Permisos de Claude Code
│   └── skills/                            # Skills reutilizables
│       ├── code-review/SKILL.md           # /code-review - Revision de codigo
│       ├── refactor/SKILL.md              # /refactor - Refactorizacion guiada
│       └── deploy/SKILL.md               # /deploy - Proceso de deploy
├── DESARROLLO-A3/                         # === ENTREGABLE AL CLIENTE ===
│   ├── docs/
│   │   ├── architecture.md               # Documento principal de arquitectura
│   │   ├── decisions/                     # ADRs (Architecture Decision Records)
│   │   └── runbooks/                      # Procedimientos operativos (deploy, etc.)
│   ├── 1-agente-conversacional/
│   │   ├── CONTEXTO.md                    # Contexto local del modulo
│   │   ├── app/                           # Codigo fuente Flask
│   │   ├── tools/                         # Scripts operativos
│   │   ├── architecture/sops/            # SOPs del agente
│   │   ├── .env / requirements.txt
│   │   └── README.md
│   ├── 2-plataforma/
│   │   ├── CONTEXTO.md                    # Contexto local del modulo
│   │   └── architecture/sops/            # SOPs del dashboard
│   └── 3-conexiones/
│       ├── CONTEXTO.md                    # Contexto local del modulo
│       └── architecture/                  # SQL schemas + SOPs de integracion
├── INTERNO-EQUIPO/                        # === SOLO EQUIPO DE DESARROLLO ===
│   ├── agents-md/                         # Instrucciones por IA
│   │   ├── CONTEXTO-UNIVERSAL.md          # Punto de entrada para cualquier IA
│   │   ├── claude.md / openai.md / gemini.md
│   │   └── blast-protocol.md
│   └── herramientas/                      # Skills y tools de productividad
├── Informacion/                           # Docs de negocio (solo lectura)
└── REFERENCIAS/                           # Material visual (solo lectura)
```

### Contexto por modulo

Cada seccion de DESARROLLO-A3/ tiene su propio `CONTEXTO.md` con contexto local (universal para cualquier IA):

- `1-agente-conversacional/CONTEXTO.md` - Estructura, flujo, dependencias del bot
- `2-plataforma/CONTEXTO.md` - Estado actual, vistas, plan de migracion
- `3-conexiones/CONTEXTO.md` - Integraciones activas, webhooks, modelo de datos

### Documentacion centralizada
- `DESARROLLO-A3/docs/architecture.md` - Vision general del sistema
- `DESARROLLO-A3/docs/decisions/` - ADRs para decisiones importantes
- `DESARROLLO-A3/docs/runbooks/` - Procedimientos operativos

### Skills disponibles
- `/code-review` - Revision de codigo con checklist adaptado a A3
- `/refactor` - Refactorizacion respetando zonas
- `/deploy` - Proceso de deploy a produccion

### Multi-IA
El equipo trabaja con multiples IAs (Claude, OpenAI, Gemini). Cada IA debe:
1. Leer `INTERNO-EQUIPO/agents-md/CONTEXTO-UNIVERSAL.md` primero
2. Leer su archivo especifico (`claude.md`, `openai.md`, `gemini.md`)
3. Leer el `CONTEXTO.md` del modulo en el que va a trabajar
