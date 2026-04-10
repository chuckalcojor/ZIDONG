# SOP 05 - Dashboard V1 Requirements

## Objective
Provide operational visibility for active requests and exceptions.

## Required Views
- Active requests grouped by status.
- Priority view (`normal` vs `urgent`).
- Courier workload view.
- Exception queue view (`error_pending_assignment`, invalid data, unknown intent).

## Minimum Metrics
- Requests by status (count).
- Average time from `received` to `assigned`.
- Number of urgent requests.
- Number of unassigned requests.

## Data Source
- Primary: `requests`.
- Timeline/supporting details: `request_events`.
