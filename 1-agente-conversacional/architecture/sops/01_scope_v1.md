# SOP 01 - Scope V1

## Objective
Implement a reliable first release that captures requests from Telegram, routes intents, applies deterministic assignment by client, and tracks operational states in Supabase.

## In Scope
- Telegram conversational entrypoint.
- Menu routing: route scheduling, accounting handoff, results, new client.
- Request creation and status tracking in Supabase.
- Deterministic courier assignment by client.
- Cutoff rule: after 17:30 schedule next business day.
- Operational dashboard data model.

## Out of Scope (V1)
- Direct integrations with Anarvet and Alegra.
- Automated accounting workflow logic.
- Full PDF results delivery orchestration.

## Required Reliability Rules
- Never infer missing business logic.
- If client has no assigned courier, create exception state and hand off to operations.
- Keep all transitions auditable via request events.
