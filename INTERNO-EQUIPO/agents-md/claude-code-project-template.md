# Template: Claude Code Project Structure

Template de estructura modular para proyectos asistidos por Claude Code.
Diseñada para mantener contexto estructurado, skills reutilizables, hooks de automatizacion y arquitectura escalable.

---

## Arquitectura general

El proyecto se organiza en 5 capas:

1. **Contexto IA** (`CLAUDE.md`, `.claude/`) - Instrucciones y configuracion para Claude
2. **Skills** (`.claude/skills/`) - Flujos de trabajo reutilizables
3. **Documentacion** (`docs/`) - Arquitectura, decisiones, runbooks
4. **Herramientas** (`tools/`) - Scripts y prompts auxiliares
5. **Codigo fuente** (`src/`) - Modulos de la aplicacion, cada uno con su propio contexto

---

## Estructura del repositorio

```text
claude_code_project/
├── CLAUDE.md                    # Memoria principal del proyecto para Claude
├── README.md                    # Vision general, proposito, onboarding
├── docs/
│   ├── architecture.md          # Documento principal de arquitectura
│   ├── decisions/               # ADRs (Architecture Decision Records)
│   │   └── 001-stack-selection.md
│   └── runbooks/                # Procedimientos operativos
│       └── deploy.md
├── .claude/
│   ├── settings.json            # Configuracion de Claude para el proyecto
│   ├── hooks/                   # Guardrails y automatizaciones
│   │   └── pre-commit.sh
│   └── skills/                  # Skills reutilizables
│       ├── code-review/
│       │   └── SKILL.md
│       ├── refactor/
│       │   └── SKILL.md
│       └── release/
│           └── SKILL.md
├── tools/
│   ├── scripts/                 # Scripts auxiliares
│   │   └── setup.sh
│   └── prompts/                 # Prompts reutilizables por proposito
│       └── analisis-de-codigo.md
└── src/
    ├── api/
    │   ├── CLAUDE.md             # Contexto especifico del modulo API
    │   └── ...
    └── persistence/
        ├── CLAUDE.md             # Contexto especifico del modulo de persistencia
        └── ...
```

---

## Contenido inicial de cada archivo

### CLAUDE.md (raiz)

```markdown
# Proyecto: [Nombre del proyecto]

## Que es
[Descripcion en 1-2 lineas]

## Stack
- Backend: [tecnologia]
- Base de datos: [tecnologia]
- Infra: [tecnologia]

## Convenciones
- Nombrado: snake_case para archivos, camelCase para variables
- Tests: obligatorios para logica de negocio
- Commits: conventional commits (feat:, fix:, refactor:)

## Estructura
- `src/api/` - Endpoints REST/GraphQL
- `src/persistence/` - Modelos, migraciones, repositorios

## Reglas para Claude
- No modificar archivos de configuracion sin confirmar
- Siempre ejecutar tests despues de cambios en src/
- Preferir editar archivos existentes antes de crear nuevos
- Documentar decisiones importantes en docs/decisions/
```

---

### README.md

```markdown
# [Nombre del proyecto]

[Descripcion breve del proyecto]

## Requisitos
- Node.js >= 20 / Python >= 3.12
- [Base de datos]
- Claude Code CLI

## Instalacion
\`\`\`bash
git clone [repo]
cd claude_code_project
./tools/scripts/setup.sh
\`\`\`

## Estructura del proyecto
Ver [docs/architecture.md](docs/architecture.md) para la arquitectura completa.

## Desarrollo con Claude Code
1. Claude lee `CLAUDE.md` para entender el proyecto
2. Los skills en `.claude/skills/` automatizan tareas repetitivas
3. Los hooks en `.claude/hooks/` validan antes de commit
4. Cada modulo en `src/` tiene su propio `CLAUDE.md` con contexto local

## Skills disponibles
- `/code-review` - Revision de codigo con checklist
- `/refactor` - Refactorizacion guiada
- `/release` - Proceso de release automatizado
```

---

### docs/architecture.md

```markdown
# Arquitectura

## Vision general
[Diagrama o descripcion de alto nivel del sistema]

## Componentes principales

### API (`src/api/`)
- Responsabilidad: [que hace]
- Patron: [REST/GraphQL/RPC]
- Autenticacion: [metodo]

### Persistencia (`src/persistence/`)
- Responsabilidad: [que hace]
- Base de datos: [cual]
- ORM/Driver: [cual]

## Flujo de datos
1. Request -> API -> Validacion -> Servicio -> Persistencia -> Response

## Decisiones de arquitectura
Ver [decisions/](decisions/) para el registro completo de ADRs.
```

---

### .claude/settings.json

```json
{
  "permissions": {
    "allow": [
      "Bash(npm test)",
      "Bash(npm run lint)",
      "Bash(npm run build)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(git push --force)"
    ]
  }
}
```

---

### .claude/skills/code-review/SKILL.md

```markdown
---
name: Code Review
description: Revision sistematica de codigo con checklist de calidad
---

# Code Review

Realiza una revision de codigo siguiendo este checklist:

## Checklist

### Correctitud
- [ ] La logica cumple con los requisitos
- [ ] Los edge cases estan cubiertos
- [ ] No hay bugs obvios

### Calidad
- [ ] Nombrado claro y consistente
- [ ] Funciones pequenas con una sola responsabilidad
- [ ] Sin codigo duplicado
- [ ] Sin imports no usados

### Seguridad
- [ ] Sin secretos hardcodeados
- [ ] Inputs validados y sanitizados
- [ ] Sin inyecciones SQL/XSS

### Tests
- [ ] Tests unitarios para logica nueva
- [ ] Tests cubren los happy paths y edge cases
- [ ] Tests pasan en CI

## Formato de salida
Para cada issue encontrado:
1. Archivo y linea
2. Severidad (critico/medio/bajo)
3. Descripcion del problema
4. Sugerencia de fix
```

---

### .claude/skills/refactor/SKILL.md

```markdown
---
name: Refactor
description: Refactorizacion guiada con preservacion de comportamiento
---

# Refactor

Guia para refactorizar codigo manteniendo el comportamiento existente.

## Proceso

1. **Analizar** - Identificar code smells y areas de mejora
2. **Tests** - Verificar que existen tests que cubran el codigo a cambiar
3. **Planificar** - Describir los cambios antes de hacerlos
4. **Ejecutar** - Aplicar cambios incrementales
5. **Verificar** - Ejecutar tests despues de cada cambio

## Code smells a buscar
- Funciones de mas de 30 lineas
- Mas de 3 niveles de indentacion
- Codigo duplicado (3+ ocurrencias)
- Clases/modulos con mas de una responsabilidad
- Parametros booleanos que cambian comportamiento

## Reglas
- Nunca cambiar comportamiento y refactorizar en el mismo paso
- Siempre ejecutar tests entre cambios
- Preferir composicion sobre herencia
- Extraer constantes magicas a variables con nombre
```

---

### .claude/skills/release/SKILL.md

```markdown
---
name: Release
description: Proceso estandarizado de release
---

# Release

Proceso para crear un release del proyecto.

## Pre-release
1. Verificar que todos los tests pasan: `npm test`
2. Verificar que el build funciona: `npm run build`
3. Revisar CHANGELOG.md esta actualizado
4. Verificar que no hay cambios sin commitear

## Proceso
1. Actualizar version en package.json
2. Actualizar CHANGELOG.md con la nueva version
3. Crear commit: `git commit -m "release: v[X.Y.Z]"`
4. Crear tag: `git tag v[X.Y.Z]`
5. Push: `git push && git push --tags`

## Post-release
1. Verificar que CI/CD completa exitosamente
2. Verificar deploy en staging/production
3. Comunicar el release al equipo

## Versionado
- MAJOR: cambios que rompen compatibilidad
- MINOR: funcionalidad nueva compatible
- PATCH: bug fixes
```

---

### src/api/CLAUDE.md

```markdown
# Modulo: API

## Responsabilidad
Expone los endpoints HTTP del proyecto. Maneja autenticacion, validacion de input, y ruteo.

## Convenciones
- Un archivo por recurso/entidad
- Validacion de input en el handler, no en el servicio
- Respuestas con formato consistente: `{ data, error, meta }`
- Codigos HTTP semanticos (201 para crear, 204 para delete, etc.)

## Dependencias
- Depende de: `src/persistence/` para acceso a datos
- No debe: importar directamente drivers de base de datos

## Tests
- Tests de integracion para cada endpoint
- Mockear la capa de persistencia en tests unitarios
```

---

### src/persistence/CLAUDE.md

```markdown
# Modulo: Persistencia

## Responsabilidad
Acceso a base de datos. Modelos, migraciones, queries y repositorios.

## Convenciones
- Un archivo por entidad/modelo
- Usar repositorio pattern (no queries directas en servicios)
- Migraciones numeradas secuencialmente
- Indices documentados en el modelo

## Dependencias
- No depende de: `src/api/` (capa inferior)
- Exporta: interfaces de repositorio

## Tests
- Tests contra base de datos de testing (no mocks)
- Cada migracion debe ser reversible
```

---

## Guia de inicio

### 1. Crear el repositorio

```bash
mkdir claude_code_project && cd claude_code_project
git init

# Crear estructura
mkdir -p docs/decisions docs/runbooks
mkdir -p .claude/hooks .claude/skills/code-review .claude/skills/refactor .claude/skills/release
mkdir -p tools/scripts tools/prompts
mkdir -p src/api src/persistence
```

### 2. Crear archivos base

```bash
# Copiar los contenidos de esta template a cada archivo
touch CLAUDE.md README.md
touch docs/architecture.md
touch .claude/settings.json
touch .claude/skills/code-review/SKILL.md
touch .claude/skills/refactor/SKILL.md
touch .claude/skills/release/SKILL.md
touch src/api/CLAUDE.md
touch src/persistence/CLAUDE.md
```

### 3. Configurar Claude

Editar `CLAUDE.md` con la informacion real del proyecto:
- Nombre y descripcion
- Stack tecnologico
- Convenciones del equipo
- Reglas especificas

### 4. Personalizar skills

Adaptar los skills a las necesidades del proyecto:
- Agregar checks especificos del stack al code-review
- Ajustar el proceso de release al CI/CD del proyecto
- Crear skills nuevos para flujos repetitivos del equipo

### 5. Agregar hooks

Crear hooks en `.claude/hooks/` para:
- Validar formato de commits
- Ejecutar linter antes de commit
- Verificar que no hay secretos en el codigo

### 6. Comenzar a construir

```bash
# Abrir con Claude Code
claude

# Claude leera CLAUDE.md automaticamente
# Usar skills con /code-review, /refactor, /release
```

---

## Buenas practicas

| Practica | Descripcion |
|----------|-------------|
| CLAUDE.md enfocado | Maximo 200 lineas. Solo lo que Claude necesita saber |
| Skills para repeticion | Si haces algo mas de 2 veces, crea un skill |
| Hooks para guardrails | Automatiza validaciones que no quieres olvidar |
| ADRs para decisiones | Documenta el "por que", no solo el "que" |
| Contexto local por modulo | Cada `src/*/CLAUDE.md` da contexto especifico |
| Prompts modulares | Un prompt por proposito en `tools/prompts/` |
| Minimo contexto necesario | Solo incluir lo relevante, no toda la documentacion |
