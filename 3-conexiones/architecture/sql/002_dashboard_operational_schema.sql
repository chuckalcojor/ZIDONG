create table if not exists liveconnect_conversations (
  id uuid primary key default gen_random_uuid(),
  external_conversation_id text unique,
  channel text not null default 'liveconnect',
  external_contact text,
  customer_name text,
  open_status text not null default 'open' check (open_status in ('open', 'closed', 'pending')),
  conversation_summary text,
  first_message_at timestamptz,
  last_message_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists liveconnect_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references liveconnect_conversations(id) on delete cascade,
  external_message_id text,
  direction text not null check (direction in ('inbound', 'outbound')),
  agent_name text,
  intent_tag text,
  message_text text not null,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists analysis_catalog (
  id uuid primary key default gen_random_uuid(),
  test_code text not null unique,
  test_name text not null,
  category text,
  subcategory text,
  sample_type text,
  turnaround_hours integer,
  price_cop integer,
  source text not null default 'catalog_pdf',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists lab_samples (
  id uuid primary key default gen_random_uuid(),
  request_id uuid references requests(id) on delete set null,
  client_id uuid references clients(id) on delete set null,
  patient_name text,
  species text,
  sample_type text,
  test_code text,
  test_name text,
  status text not null check (status in ('pending_pickup', 'on_route', 'received_lab', 'in_analysis', 'ready_results', 'delivered_results', 'cancelled')),
  priority text not null default 'normal' check (priority in ('normal', 'urgent')),
  assigned_courier_id uuid references couriers(id),
  estimated_ready_at timestamptz,
  delivered_at timestamptz,
  source_system text,
  source_reference text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists lab_sample_events (
  id uuid primary key default gen_random_uuid(),
  sample_id uuid not null references lab_samples(id) on delete cascade,
  event_type text not null,
  event_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_liveconnect_messages_conversation on liveconnect_messages(conversation_id);
create index if not exists idx_liveconnect_messages_created_at on liveconnect_messages(created_at desc);
create index if not exists idx_lab_samples_status on lab_samples(status);
create index if not exists idx_lab_samples_created_at on lab_samples(created_at desc);
create index if not exists idx_lab_sample_events_sample on lab_sample_events(sample_id);
