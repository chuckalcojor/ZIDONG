# AGENTS.md - <PROJECT_NAME>

## Resumen del proyecto
- Objetivo: <OBJETIVO_CORTO>
- Stack: <STACK_PRINCIPAL>
- Version minima: <VERSIONES_RELEVANTES>

## Setup y desarrollo
- Instalar dependencias: `<CMD_INSTALL>`
- Iniciar entorno local: `<CMD_DEV>`
- Variables de entorno: `<RUTA_ENV_O_GESTOR_SECRETOS>`

## Calidad (obligatorio antes de finalizar)
- Lint: `<CMD_LINT>`
- Typecheck: `<CMD_TYPECHECK_O_NA>`
- Tests: `<CMD_TEST>`
- Build local (si aplica): `<CMD_BUILD_O_NA>`

## Convenciones de codigo
- Lenguaje/estilo: <REGLAS_ESTILO>
- Arquitectura: <PATRONES_PERMITIDOS>
- Evitar: <ANTI_PATRONES>

## Reglas de cambios
- No modificar: <RUTAS_SENSIBLES_O_GENERADAS>
- Migraciones: <POLITICA_MIGRACIONES>
- Dependencias nuevas: <CRITERIO_APROBACION>

## Seguridad y datos
- Nunca commitear secretos (`.env`, llaves, tokens)
- Mascaras de datos sensibles en logs
- Revisar permisos y validaciones de entrada/salida

## Flujo de trabajo
- Commits: <FORMATO_COMMIT>
- PR: <FORMATO_PR>
- Definicion de terminado: checks en verde + cambios documentados

## Monorepo (si aplica)
- Package principal: <PACKAGE_O_SERVICIO>
- Comandos por paquete: <COMANDOS_CON_FILTER>
- Regla de precedencia: AGENTS.md mas cercano al archivo editado

## Referencias
- README: `./README.md`
- Arquitectura: `<RUTA_DOCS_ARQ>`
- CI/CD: `<RUTA_WORKFLOWS_O_PIPELINE_DOCS>`
