create table if not exists telegram_sessions (
  id uuid primary key default gen_random_uuid(),
  channel text not null default 'telegram',
  external_chat_id text not null unique,
  client_id uuid references clients(id) on delete set null,
  request_id uuid references requests(id) on delete set null,
  intent_current text not null default 'no_clasificado',
  service_area text not null default 'unknown' check (service_area in ('route_scheduling', 'accounting', 'results', 'new_client', 'unknown')),
  phase_current text not null default 'fase_1_clasificacion',
  phase_next text,
  status text not null default 'in_progress' check (status in ('in_progress', 'confirmed', 'closed', 'escalated')),
  missing_fields jsonb not null default '[]'::jsonb,
  captured_fields jsonb not null default '{}'::jsonb,
  ai_confidence numeric(4,3),
  requires_handoff boolean not null default false,
  handoff_area text not null default 'none' check (handoff_area in ('none', 'contabilidad', 'tecnico', 'operaciones')),
  next_action text,
  last_user_message text,
  last_bot_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_telegram_sessions_client on telegram_sessions(client_id);
create index if not exists idx_telegram_sessions_intent on telegram_sessions(intent_current);
create index if not exists idx_telegram_sessions_phase on telegram_sessions(phase_current);
create index if not exists idx_telegram_sessions_status on telegram_sessions(status);
