# Runbook: Deploy

## Pre-deploy
1. Verificar que no hay cambios sin commitear: `git status`
2. Verificar que el .env tiene todas las variables requeridas
3. Revisar que los SQL schemas en 3-conexiones/ estan sincronizados con Supabase

## Deploy del agente conversacional
1. cd a `DESARROLLO-A3/1-agente-conversacional/`
2. Instalar dependencias: `pip install -r requirements.txt`
3. Ejecutar: `python -m app.main`
4. Verificar health: `GET /health` → `{"status": "ok"}`
5. Configurar webhook Telegram: `python tools/set_telegram_webhook.py`

## Variables de entorno requeridas
- `TELEGRAM_BOT_TOKEN` - Token del bot de Telegram
- `TELEGRAM_WEBHOOK_SECRET` - Secret para validar webhooks
- `SUPABASE_URL` - URL de la instancia Supabase
- `SUPABASE_SERVICE_ROLE_KEY` - Service role key de Supabase
- `OPENAI_API_KEY` - API key de OpenAI
- `FLASK_SECRET_KEY` - Secret para sesiones Flask
- `DASHBOARD_ADMIN_USER` / `DASHBOARD_ADMIN_PASSWORD` - Credenciales del dashboard

## Post-deploy
1. Enviar mensaje de prueba al bot de Telegram
2. Verificar que el dashboard carga en `/dashboard`
3. Revisar logs en Render
