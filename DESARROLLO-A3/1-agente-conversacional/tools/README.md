# Tools Layer (Deterministic)

This folder contains atomic Python scripts used by the Navigation layer.

## Current V1 Scripts

- `intake_router.py`: maps incoming menu/message text to a deterministic service area.
- `schedule_business_day.py`: calculates pickup date using cutoff 17:30 and next-business-day logic.
- `assignment_engine.py`: assigns courier by client assignment or emits fallback state.
- `import_clients_excel.py`: loads client list + courier assignment from provided Excel.
- `import_route_assignments_excel.py`: imports `A3 VETERINARIA.xlsx` (manual client-courier assignment) into `clients`, `couriers`, and `client_courier_assignment`.
- `import_catalog_pdf.py`: extracts catalog tests and prices from provided PDF.
- `link_check.py`: validates Telegram and Supabase reachability.
- `set_telegram_webhook.py`: registers Telegram webhook URL.
- `dev_localtunnel_webhook.py`: creates localtunnel, registers webhook, and persists URL in `.env`.
- `build_clients_a3_index.py`: builds a normalized SQLite index from `Clientes a3.xlsx` for fast lookup of clinics, professionals, and sample status events.
- `query_clients_a3_index.py`: queries the normalized SQLite index by clinic and sample status.
- `sync_clients_a3_index_to_supabase.py`: syncs the normalized SQLite index into Supabase tables (`clients_a3_knowledge`, `clients_a3_professionals`, `clients_a3_sample_events`).
- `evaluate_gpt5_conversation.py`: executes stress benchmark (single-turn, multi-turn and quality dimensions: comprehension, coherence, naturality, utility, safety).

## Usage Pattern

Each script receives JSON via `stdin` and writes JSON to `stdout`.

Example:

```bash
python tools/intake_router.py < .tmp/router_input.json
```

## Clients A3 Index

Build index:

```bash
py tools/build_clients_a3_index.py --excel "C:\Users\gasto\OneDrive\Desktop\Clientes  a3.xlsx"
```

Query clinic profile:

```bash
py tools/query_clients_a3_index.py --mode clinic --clinic "my pet city"
```

Query sample status:

```bash
py tools/query_clients_a3_index.py --mode sample_status --clinic "my pet city"
```

Import manual route assignments workbook:

```bash
py tools/import_route_assignments_excel.py --excel "C:\Users\gasto\Downloads\A3 VETERINARIA.xlsx"
```

Sync to Supabase (after applying `3-conexiones/architecture/sql/006_clients_a3_knowledge_index.sql`):

```bash
py tools/sync_clients_a3_index_to_supabase.py
```

Run conversational benchmark:

```bash
py tools/evaluate_gpt5_conversation.py --areas all --single-turn-samples 80 --multiturn-samples 20 --offline-stub
```

Run benchmark without quality suite (faster):

```bash
py tools/evaluate_gpt5_conversation.py --areas route_scheduling,results --single-turn-samples 40 --skip-quality-suite --offline-stub
```
