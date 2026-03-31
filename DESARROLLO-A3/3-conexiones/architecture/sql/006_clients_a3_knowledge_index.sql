create table if not exists clients_a3_knowledge (
  clinic_key text primary key,
  clinic_name text not null,
  is_registered boolean not null default false,
  is_new_client boolean not null default false,
  address text,
  locality text,
  phone text,
  email text,
  payment_policy text,
  result_delivery_mode text,
  sources_json jsonb not null default '[]'::jsonb,
  source_excel text,
  source_updated_at timestamptz,
  synced_at timestamptz not null default now()
);

create table if not exists clients_a3_professionals (
  id uuid primary key default gen_random_uuid(),
  clinic_key text not null references clients_a3_knowledge(clinic_key) on delete cascade,
  professional_key text not null,
  professional_name text,
  professional_card text,
  source_sheet text not null,
  synced_at timestamptz not null default now(),
  unique (clinic_key, professional_key, source_sheet)
);

create table if not exists clients_a3_sample_events (
  event_key text primary key,
  source_sheet text not null,
  clinic_key text,
  clinic_name_raw text,
  patient_name text,
  exam_code text,
  exam_number text,
  pending_exam text,
  status_bucket text not null check (status_bucket in ('submitted', 'pending_issue')),
  reason text,
  registered_flag text,
  observation text,
  synced_at timestamptz not null default now()
);

create index if not exists idx_clients_a3_knowledge_name on clients_a3_knowledge(clinic_name);
create index if not exists idx_clients_a3_prof_clinic on clients_a3_professionals(clinic_key);
create index if not exists idx_clients_a3_events_clinic on clients_a3_sample_events(clinic_key);
create index if not exists idx_clients_a3_events_status on clients_a3_sample_events(status_bucket);
create index if not exists idx_clients_a3_events_exam on clients_a3_sample_events(exam_number);
