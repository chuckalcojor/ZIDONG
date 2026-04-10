# ADR 006 - Preparacion de canal para WhatsApp Business (sin dependencia de LiveConnect)

## Estado
Aprobado

## Contexto
Se confirmo que LiveConnect probablemente no sera el canal definitivo. Se requiere dejar la base lista para WhatsApp Business u otro canal conversacional.

## Decision

1. Mantener `LiveConnect` como legado temporal, sin nuevas dependencias criticas.
2. Agregar endpoints de webhook para WhatsApp Business:
   - `GET /webhooks/whatsapp` para verificacion `hub.challenge`.
   - `POST /webhooks/whatsapp` para recepcion de mensajes.
3. Registrar trazabilidad de mensajes WhatsApp en el mismo esquema operativo (`request_events` y `telegram_message_events` con `channel=whatsapp`).
4. Enviar acuse de recibo por API de WhatsApp solo si hay credenciales configuradas.

## Consecuencias

### Positivas
- El sistema queda listo para migrar canal sin bloquear desarrollo del flujo de negocio.
- Se conserva trazabilidad centralizada independiente del canal.

### Riesgos
- Sin credenciales reales, el acuse saliente se omite (comportamiento esperado en entorno local/mock).

## Mitigaciones
- Variables de entorno opcionales para activacion gradual.
- Endpoint tolerante a fallos de persistencia para no romper ingestion.
