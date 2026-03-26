create table if not exists conversation_stage_events (
  id uuid primary key default gen_random_uuid(),
  channel text not null default 'telegram' check (channel in ('telegram', 'whatsapp', 'liveconnect', 'manual')),
  external_chat_id text not null,
  client_id uuid references clients(id) on delete set null,
  request_id uuid references requests(id) on delete set null,
  from_stage text,
  to_stage text not null,
  trigger_source text not null default 'openai_turn',
  trigger_message text,
  created_at timestamptz not null default now()
);

create index if not exists idx_conv_stage_events_chat on conversation_stage_events(external_chat_id);
create index if not exists idx_conv_stage_events_to_stage on conversation_stage_events(to_stage);
create index if not exists idx_conv_stage_events_created_at on conversation_stage_events(created_at desc);
create index if not exists idx_conv_stage_events_client on conversation_stage_events(client_id);
