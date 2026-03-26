# Tools Layer (Deterministic)

This folder contains atomic Python scripts used by the Navigation layer.

## Current V1 Scripts

- `intake_router.py`: maps incoming menu/message text to a deterministic service area.
- `schedule_business_day.py`: calculates pickup date using cutoff 17:30 and next-business-day logic.
- `assignment_engine.py`: assigns courier by client assignment or emits fallback state.
- `import_clients_excel.py`: loads client list + courier assignment from provided Excel.
- `import_catalog_pdf.py`: extracts catalog tests and prices from provided PDF.
- `link_check.py`: validates Telegram and Supabase reachability.
- `set_telegram_webhook.py`: registers Telegram webhook URL.
- `dev_localtunnel_webhook.py`: creates localtunnel, registers webhook, and persists URL in `.env`.

## Usage Pattern

Each script receives JSON via `stdin` and writes JSON to `stdout`.

Example:

```bash
python tools/intake_router.py < .tmp/router_input.json
```
