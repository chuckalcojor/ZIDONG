# SOP 06 - QA Cases V1

## Mandatory Test Cases

1. Existing client with assigned courier
- Expected: request created, status `assigned`, courier linked.

2. Existing client without assigned courier
- Expected: status `error_pending_assignment`, exception event created.

3. New client flow
- Expected: onboarding data captured, marked for manual assignment.

4. Invalid or incomplete pickup data
- Expected: validation message, no broken request creation.

5. After-cutoff request (post 17:30)
- Expected: `scheduled_pickup_date` equals next business day.

6. Service area routing
- Expected: menu options route correctly to: route scheduling, accounting handoff, results, new client.
