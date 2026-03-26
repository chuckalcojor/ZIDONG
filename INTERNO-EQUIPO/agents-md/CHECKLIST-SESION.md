# Checklist de Sesion (Copiar al inicio)

Usa este bloque al arrancar cada sesion con cualquier IA (Claude, Codex/OpenAI o Gemini).

```markdown
CHECKLIST DE SESION - A3 VETERINARIA

1) Canonico activo: `AGENTS.md` (raiz).
   - Base metodologica extra: `Template de Proyecto/templates/reglas.md` y `Template de Proyecto/templates/workflows.md`.
2) Confirmar IA y adaptador:
   - Claude -> `INTERNO-EQUIPO/agents-md/claude.md`
   - OpenAI/Codex -> `INTERNO-EQUIPO/agents-md/openai.md`
   - Gemini -> `INTERNO-EQUIPO/agents-md/gemini.md`
3) Leer `INTERNO-EQUIPO/agents-md/CONTEXTO-UNIVERSAL.md`.
4) Definir zona de trabajo (una sola por tarea):
   - `DESARROLLO-A3/1-agente-conversacional/`
   - `DESARROLLO-A3/2-plataforma/`
   - `DESARROLLO-A3/3-conexiones/`
5) Leer `CONTEXTO.md` de la zona elegida.
6) Revisar SOPs de la zona antes de tocar codigo.
7) Reglas no negociables:
   - No mezclar `DESARROLLO-A3/` con `INTERNO-EQUIPO/`.
   - No modificar `Informacion/` ni `REFERENCIAS/`.
   - No hardcodear secretos (solo `.env`).
8) Si hay cambios de BD, documentar primero en `DESARROLLO-A3/3-conexiones/`.
9) Implementar solo el alcance pedido, con cambios minimos y coherentes.
10) Verificar con comandos existentes del modulo (tests/lint/checks aplicables).
11) Reportar evidencia de verificacion (que corrio, que paso, que fallo).
12) Si hay decision relevante de arquitectura, registrar ADR en `DESARROLLO-A3/docs/decisions/`.
13) En bugs: buscar causa raiz, aplicar fix minimo y volver a verificar.
```

## Version ultra-corta (si estas con prisa)

1. `AGENTS.md` manda.
2. Leer `CONTEXTO-UNIVERSAL.md` + adaptador IA.
3. Elegir zona y leer su `CONTEXTO.md` + SOPs.
4. No mezclar zonas ni tocar carpetas de solo lectura.
5. Verificar y reportar evidencia antes de cerrar.
