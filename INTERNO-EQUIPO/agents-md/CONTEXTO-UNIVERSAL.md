# Contexto Universal del Proyecto - LEER PRIMERO

Este archivo es el punto de entrada para CUALQUIER IA que trabaje en este proyecto.
Independientemente de si eres Claude, GPT, Gemini u otra IA, lee este archivo completo antes de hacer cualquier cosa.

---

## Proyecto
**LABERIT A3 VETERINARIA** - Plataforma integral para A3 Laboratorio Veterinario (Colombia).

## Que estamos construyendo

1. **Agente conversacional** - Bot que atiende clientes por Telegram/WhatsApp (programar rutas, resultados, contabilidad, altas)
2. **Plataforma/Dashboard** - Panel operativo para el equipo de A3 (metricas, clientes, muestras, analisis)
3. **Conexiones** - Integraciones con Supabase, OpenAI, Telegram, LiveConnect, Anarvet, Alegra

## Stack tecnico

- Backend: Python 3.14 + Flask
- Base de datos: Supabase (PostgreSQL)
- IA del producto: OpenAI API (gpt-4.1-mini)
- Mensajeria: Telegram Bot API (migracion a WhatsApp Business API planificada)
- Frontend futuro: Next.js + React + Tailwind
- Infra: Render + Supabase hosted

## Estructura completa del repositorio

```text
LABERIT A3 VETERINARIA/
├── CLAUDE.md                              # Reglas del proyecto (leer tambien)
├── .claude/
│   ├── settings.local.json                # Permisos de Claude Code
│   └── skills/                            # Skills reutilizables
│       ├── code-review/SKILL.md           # Revision de codigo
│       ├── refactor/SKILL.md              # Refactorizacion guiada
│       └── deploy/SKILL.md               # Proceso de deploy
│
├── DESARROLLO-A3/                         # === ENTREGABLE AL CLIENTE ===
│   ├── docs/
│   │   ├── architecture.md               # Arquitectura general del sistema
│   │   ├── decisions/                     # ADRs (Architecture Decision Records)
│   │   │   ├── 001-stack-selection.md
│   │   │   └── 002-project-restructure.md
│   │   └── runbooks/
│   │       └── deploy.md                 # Procedimiento de deploy
│   ├── 1-agente-conversacional/
│   │   ├── CONTEXTO.md                    # Contexto local del bot
│   │   ├── app/                           # Flask app (main, logic, ai_prompt, config)
│   │   │   └── services/                 # Clientes API (openai, supabase, telegram)
│   │   ├── tools/                         # Scripts operativos
│   │   ├── architecture/sops/            # SOPs del agente
│   │   ├── .env / requirements.txt
│   │   └── README.md
│   ├── 2-plataforma/
│   │   ├── CONTEXTO.md                    # Contexto local del dashboard
│   │   └── architecture/sops/            # SOPs del dashboard
│   └── 3-conexiones/
│       ├── CONTEXTO.md                    # Contexto local de integraciones
│       └── architecture/
│           ├── sql/                       # SQL schemas (001_, 002_, 003_)
│           └── sops/                      # SOPs de modelo de datos y contratos
│
├── INTERNO-EQUIPO/                        # === SOLO EQUIPO DE DESARROLLO ===
│   ├── agents-md/                         # <-- ESTAS AQUI. Instrucciones por IA
│   │   ├── CONTEXTO-UNIVERSAL.md          # Este archivo
│   │   ├── claude.md                      # Instrucciones para Claude
│   │   ├── openai.md                      # Instrucciones para GPT/OpenAI
│   │   ├── gemini.md                      # Project Map para Gemini
│   │   ├── blast-protocol.md              # Metodologia B.L.A.S.T.
│   │   └── claude-code-project-template.md
│   └── herramientas/                      # 27 skills de productividad del equipo
│       ├── 1-whatsapp-agent/             # 9 skills: agentes conversacionales
│       ├── 2-dashboard-plataforma/       # 11 skills: dashboard (frontend + backend)
│       └── 3-multi-agentes-productividad/ # 7 skills: orquestacion y productividad
│
├── Informacion/                           # Docs de negocio (solo lectura)
│   ├── A3 - Catalogo 2025.pdf
│   ├── ETAPAS LABERIT.pdf
│   └── Relacion Clientes.xlsx
└── REFERENCIAS/                           # Material visual (solo lectura)
    └── Ejemplo de Plataforma.jpg
```

## Reglas que TODA IA debe respetar

1. **NUNCA mezclar** codigo de DESARROLLO-A3/ con INTERNO-EQUIPO/
2. **NUNCA importar** modulos internos del equipo en el codigo del producto
3. **Las herramientas internas** (skills, prompts, agents-md) NO son parte del producto
4. **Antes de tocar la BD**, documentar en `DESARROLLO-A3/3-conexiones/`
5. **Antes de tocar el dashboard**, revisar SOPs en `DESARROLLO-A3/2-plataforma/`
6. **Antes de tocar el bot**, revisar SOPs en `DESARROLLO-A3/1-agente-conversacional/`
7. **No modificar** Informacion/ ni REFERENCIAS/ (solo lectura)
8. **Cada modulo tiene su CONTEXTO.md** - leerlo antes de trabajar en ese modulo
9. **Las decisiones importantes** se documentan como ADRs en `DESARROLLO-A3/docs/decisions/`
10. **Conventional commits**: feat:, fix:, refactor:, docs:

## Como empezar a trabajar

1. Lee este archivo completo (ya lo estas haciendo)
2. Lee `AGENTS.md` en la raiz (fuente canonica multi-IA)
3. Lee tu archivo especifico de IA (`claude.md`, `openai.md`, `gemini.md`)
4. Lee `CLAUDE.md` en la raiz (adaptador y reglas detalladas)
5. Lee el `CONTEXTO.md` del modulo en el que vas a trabajar
6. Si necesitas entender la arquitectura: `DESARROLLO-A3/docs/architecture.md`
7. Si necesitas entender una decision pasada: `DESARROLLO-A3/docs/decisions/`

## Donde encontrar mas contexto

- `CLAUDE.md` (raiz) - Reglas detalladas del proyecto y convenciones
- `AGENTS.md` (raiz) - Fuente canonica de contexto para cualquier IA
- `INTERNO-EQUIPO/agents-md/CHECKLIST-SESION.md` - Checklist corta para pegar al inicio de cada sesion
- `Template de Proyecto/templates/reglas.md` - Reglas base de trabajo
- `Template de Proyecto/templates/workflows.md` - Flujo operativo recomendado
- `DESARROLLO-A3/docs/architecture.md` - Arquitectura completa con diagramas
- `DESARROLLO-A3/docs/decisions/` - ADRs de decisiones importantes
- `DESARROLLO-A3/docs/runbooks/deploy.md` - Como deployar
- `INTERNO-EQUIPO/agents-md/claude.md` - Instrucciones especificas para Claude
- `INTERNO-EQUIPO/agents-md/openai.md` - Instrucciones especificas para GPT/OpenAI
- `INTERNO-EQUIPO/agents-md/gemini.md` - Instrucciones especificas para Gemini
- `INTERNO-EQUIPO/agents-md/blast-protocol.md` - Protocolo B.L.A.S.T. (metodologia)

## Skills disponibles (INTERNO-EQUIPO/herramientas/)

27 skills de productividad del equipo. Cada skill tiene un `SKILL.md` con instrucciones detalladas. Para usar una skill, lee su SKILL.md y sigue las instrucciones.

**1-whatsapp-agent/** (9 skills): agent-memory-systems, ai-agent-development, langgraph, prompt-engineering-patterns, rag-engineer, visualization-expert, automate-whatsapp, observe-whatsapp, whatsapp-automation

**2-dashboard-plataforma/** (11 skills): api-design-principles, fastapi-pro, graphql-architect, nodejs-best-practices, kpi-dashboard-design, nextjs-best-practices, nextjs-supabase-auth, react-best-practices, react-flow-architect, tailwind-design-system, ui-ux-pro-max

**3-multi-agentes-productividad/** (7 skills): agent-orchestration, brainstorming, dispatching-parallel-agents, executing-plans, multi-agent-brainstorming, planning-with-files, subagent-driven-development

## Estado actual del proyecto (actualizar manualmente)

- V1 backend scaffold implementado
- Bot Telegram funcional con flujo conversacional IA (OpenAI)
- Dashboard operativo basico (HTML/CSS/Flask templates)
- Estructura del proyecto reorganizada con separacion clara de zonas
- Documentacion de arquitectura, ADRs y runbooks creados
- Pendiente: credenciales WhatsApp Business, migracion frontend a Next.js
