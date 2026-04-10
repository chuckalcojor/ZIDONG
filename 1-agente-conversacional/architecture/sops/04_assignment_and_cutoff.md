# SOP 04 - Assignment and Cutoff Rules (V1)

## Assignment Rule
- Source of truth: `client_courier_assignment`.
- If assignment exists: set `assigned_courier_id`, move status to `assigned`.
- If assignment does not exist: set status `error_pending_assignment`, create internal exception event.

## Priority Rule
- Allowed values: `normal`, `urgent`.
- `urgent` must be visible in dashboard filters and event logs.

## Cutoff Rule
- Local cutoff time: `17:30`.
- If request is received after cutoff: schedule pickup for next business day.
- Business day definition in V1: Monday-Friday (holidays pending external calendar source).

## Deterministic Constraints
- No random courier selection.
- No auto-reassignment in V1.
- No silent failures: every exception must create `request_events` entry.
