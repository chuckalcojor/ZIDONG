create table if not exists courier_locality_coverage (
  locality_code text primary key,
  locality_name text not null,
  courier_id uuid not null references couriers(id) on delete cascade,
  assigned_by text,
  assigned_at timestamptz not null default now()
);

create index if not exists idx_courier_locality_coverage_courier
  on courier_locality_coverage(courier_id);
