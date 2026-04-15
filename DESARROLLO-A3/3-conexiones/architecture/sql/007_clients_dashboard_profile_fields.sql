alter table if exists clients_a3_knowledge
  add column if not exists client_code text,
  add column if not exists commercial_name text,
  add column if not exists client_type text,
  add column if not exists billing_email text,
  add column if not exists vat_regime text,
  add column if not exists electronic_invoicing boolean,
  add column if not exists invoicing_rut_url text,
  add column if not exists registration_timestamp timestamptz,
  add column if not exists registration_date date,
  add column if not exists registration_time time,
  add column if not exists observations text,
  add column if not exists entered_flag boolean;

create index if not exists idx_clients_a3_knowledge_client_code
  on clients_a3_knowledge(client_code);

create index if not exists idx_clients_a3_knowledge_commercial_name
  on clients_a3_knowledge(commercial_name);

create index if not exists idx_clients_a3_knowledge_registration_date
  on clients_a3_knowledge(registration_date);
