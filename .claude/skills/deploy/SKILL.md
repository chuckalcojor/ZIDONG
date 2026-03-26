---
name: Deploy A3
description: Proceso de deploy del agente conversacional A3 a produccion
---

# Deploy A3

Proceso para deployar cambios del proyecto A3 a produccion.

## Pre-deploy
1. Verificar que no hay cambios sin commitear: `git status`
2. Confirmar que el .env de produccion tiene todas las variables
3. Revisar si hay migraciones SQL pendientes en `DESARROLLO-A3/3-conexiones/architecture/sql/`
4. Si hay SQL nuevo, ejecutar primero en Supabase

## Deploy
1. Push al branch principal
2. Render detecta el push y hace deploy automatico
3. Verificar health: `GET /health` → `{"status": "ok"}`

## Post-deploy
1. Enviar mensaje de prueba al bot de Telegram
2. Verificar dashboard en `/dashboard`
3. Revisar logs en Render por errores
4. Si hay webhooks nuevos, verificar que los secrets estan configurados

## Rollback
1. En Render: usar "Deploy previous commit"
2. Si hay migracion SQL: ejecutar rollback manual en Supabase
3. Notificar al equipo
