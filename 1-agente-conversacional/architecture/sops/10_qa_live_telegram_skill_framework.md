# SOP 10 - QA Live Telegram (Skill Framework)

## Objetivo

Validar que el bot de Telegram responde en tiempo real, clasifica bien la intencion y mantiene tono conversacional.

## Framework operativo aplicado

1. `brainstorming`: definir criterios de exito antes de ejecutar pruebas.
2. `dispatching-parallel-agents`: separar fallas por dominio (Telegram, OpenAI, Supabase, tono).
3. `refactor-a3`: aplicar fixes pequenos y verificables por modulo.
4. `code-review-a3`: revisar riesgos antes de cerrar cambios.

## Criterios de exito

- Tiempo de respuesta: <= 5s en pruebas locales estables.
- Clasificacion correcta en menu principal (rutas, contabilidad, resultados, cliente nuevo).
- Persistencia de sesion en `telegram_sessions`.
- Registro de eventos en `request_events`.
- Mensaje natural (1-3 frases, sin plantilla repetitiva).

## Setup de prueba local

Terminal A:

```bash
py -m app.main
```

Terminal B:

```bash
py tools/set_telegram_webhook.py
```

## Casos de prueba minimos

1. `Hola`
   - Esperado: saludo natural y pregunta unica de avance.

2. `Programacion de ruta`
   - Esperado: intent `programacion_rutas`, solicitud de datos minimos.

3. `Necesito resultados de Rocky orden 12345`
   - Esperado: intent `resultados`, pide solo dato faltante clave.

4. `Quiero hablar con contabilidad`
   - Esperado: escalado claro, `requires_handoff=true`.

5. Mensaje ambiguo
   - Esperado: clasificacion `no_clasificado` y respuesta amable de reconduccion.

## Diagnostico rapido si no responde

1. Ver `http://127.0.0.1:8000/health`.
2. Confirmar `getWebhookInfo` con `url` apuntando a `/webhooks/telegram`.
3. Verificar que `X-Telegram-Bot-Api-Secret-Token` coincida con `TELEGRAM_WEBHOOK_SECRET`.
4. Revisar error de OpenAI (schema/payload) en consola.

## Cierre de ronda QA

- Registrar resultado por caso: PASS/FAIL + evidencia corta.
- Si hay FAIL: causa raiz + fix minimo + re-test inmediato.
