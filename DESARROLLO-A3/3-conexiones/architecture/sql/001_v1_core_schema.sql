create extension if not exists pgcrypto;

create table if not exists clients (
  id uuid primary key default gen_random_uuid(),
  external_code text,
  clinic_name text not null,
  tax_id text,
  phone text unique,
  address text not null,
  city text,
  zone text,
  billing_type text not null check (billing_type in ('credit', 'cash')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists couriers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone text not null unique,
  availability text not null default 'available' check (availability in ('available', 'busy', 'offline')),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists client_courier_assignment (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null unique references clients(id) on delete cascade,
  courier_id uuid not null references couriers(id),
  assigned_by text,
  assigned_at timestamptz not null default now()
);

create table if not exists requests (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references clients(id),
  entry_channel text not null check (entry_channel in ('telegram', 'liveconnect', 'manual')),
  service_area text not null check (service_area in ('route_scheduling', 'accounting', 'results', 'new_client', 'unknown')),
  intent text,
  priority text not null default 'normal' check (priority in ('normal', 'urgent')),
  status text not null check (status in ('received', 'assigned', 'on_route', 'picked_up', 'in_lab', 'processed', 'sent', 'cancelled', 'error_pending_assignment')),
  exam_type text,
  exam_code text,
  patient_name text,
  pickup_address text,
  requested_at timestamptz,
  scheduled_pickup_date date,
  assigned_courier_id uuid references couriers(id),
  fallback_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists request_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references requests(id) on delete cascade,
  event_type text not null,
  event_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_requests_status on requests(status);
create index if not exists idx_requests_priority on requests(priority);
create index if not exists idx_requests_created_at on requests(created_at);
create index if not exists idx_events_request_id on request_events(request_id);
create unique index if not exists uq_clients_external_code on clients(external_code) where external_code is not null;
