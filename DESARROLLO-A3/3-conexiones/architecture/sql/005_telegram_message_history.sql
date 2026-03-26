create table if not exists telegram_message_events (
  id uuid primary key default gen_random_uuid(),
  channel text not null default 'telegram' check (channel in ('telegram', 'whatsapp', 'liveconnect', 'manual')),
  external_chat_id text not null,
  client_id uuid references clients(id) on delete set null,
  request_id uuid references requests(id) on delete set null,
  direction text not null check (direction in ('user', 'bot', 'system')),
  message_text text not null,
  phase_snapshot text,
  intent_snapshot text,
  service_area_snapshot text,
  captured_fields_snapshot jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_tg_message_events_chat_time on telegram_message_events(external_chat_id, created_at desc);
create index if not exists idx_tg_message_events_request on telegram_message_events(request_id);
create index if not exists idx_tg_message_events_direction on telegram_message_events(direction);
