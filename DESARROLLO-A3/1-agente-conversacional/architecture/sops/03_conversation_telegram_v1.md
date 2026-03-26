# SOP 03 - Telegram Conversation Flow (V1)

## Entry
Client sends greeting or message to Telegram bot.

## Primary Menu
- `Programacion de ruta`
- `Contabilidad`
- `Resultados`
- `Cliente nuevo`

## Behavior by Option

1. `Programacion de ruta`
- Capture minimum fields: clinic/client identity, pickup address, exam type, priority, requested time window.
- Validate required fields.
- Create request with status `received`.

2. `Contabilidad`
- Human handoff only in V1.
- Register event and create request with `service_area=accounting` and status `received`.

3. `Resultados`
- Capture reference data (client + patient/order if provided).
- Return current status if available.
- Keep payload contract ready for future PDF sending logic.

4. `Cliente nuevo`
- Capture onboarding fields: clinic name, phone, address, zone, billing type.
- Mark for internal review and manual courier assignment.

## Fallback
- If message cannot be classified, route to `unknown` and hand off to human.

## Conversational Stage Tracking (V1.1)

- The client must never see technical stage names.
- The bot keeps natural conversation while internal stages are tracked.
- Current stage is stored in `telegram_sessions.phase_current`.
- Every real stage change is recorded in `conversation_stage_events` for audit and dashboard flow view.
- No duplicate stage event is allowed when the stage remains unchanged.
