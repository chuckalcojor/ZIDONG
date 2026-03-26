# ADR-001: Seleccion de stack tecnologico

## Estado
Aceptado (2026-03-20)

## Contexto
A3 Laboratorio Veterinario necesita un sistema que automatice su operacion. Se requiere velocidad de desarrollo, integraciones con APIs externas y capacidad de IA conversacional.

## Decision
- **Backend**: Python 3.14 + Flask (rapido de prototipar, buen ecosistema para IA)
- **Base de datos**: Supabase (PostgreSQL hosted, auth, realtime, storage)
- **IA**: OpenAI API gpt-4.1-mini (balance costo/calidad para conversacion)
- **Mensajeria**: Telegram Bot API (V1), migracion a WhatsApp Business API (V2)
- **Frontend futuro**: Next.js + React + Tailwind (cuando se separe del Flask)
- **Infra**: Render (backend) + Supabase (datos)

## Consecuencias
- Flask sirve HTML directamente (monolito temporal) hasta separar frontend
- Supabase como unica fuente de verdad para todos los datos
- OpenAI como dependencia critica para el flujo conversacional
