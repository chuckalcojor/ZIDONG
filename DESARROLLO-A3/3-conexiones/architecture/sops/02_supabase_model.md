# SOP 02 - Supabase Data Model (V1)

## Tables

1. `clients`
- `id` uuid pk
- `external_code` text
- `clinic_name` text not null
- `tax_id` text
- `phone` text unique (nullable for legacy records)
- `address` text not null
- `city` text
- `zone` text
- `billing_type` text check in (`credit`, `cash`)
- `is_active` boolean default true
- timestamps

2. `couriers`
- `id` uuid pk
- `name` text not null
- `phone` text unique not null
- `availability` text check in (`available`, `busy`, `offline`)
- `is_active` boolean default true
- timestamps

3. `client_courier_assignment`
- `id` uuid pk
- `client_id` uuid fk -> `clients.id` unique
- `courier_id` uuid fk -> `couriers.id`
- `assigned_by` text
- `assigned_at` timestamptz default now()

4. `courier_locality_coverage`
- `locality_code` text pk (catalogo cerrado de localidades de Bogota)
- `locality_name` text not null
- `courier_id` uuid fk -> `couriers.id`
- `assigned_by` text
- `assigned_at` timestamptz default now()

5. `requests`
- `id` uuid pk
- `client_id` uuid fk -> `clients.id`
- `entry_channel` text check in (`telegram`, `liveconnect`, `manual`)
- `service_area` text check in (`route_scheduling`, `accounting`, `results`, `new_client`, `unknown`)
- `intent` text
- `priority` text check in (`normal`, `urgent`) default `normal`
- `status` text
- `exam_type` text
- `exam_code` text
- `patient_name` text
- `pickup_address` text
- `requested_at` timestamptz
- `scheduled_pickup_date` date
- `assigned_courier_id` uuid fk -> `couriers.id`
- `fallback_reason` text
- timestamps

6. `request_events`
- `id` uuid pk
- `request_id` uuid fk -> `requests.id`
- `event_type` text
- `event_payload` jsonb
- `created_at` timestamptz default now()

## Status Catalog
- `received`
- `assigned`
- `on_route`
- `picked_up`
- `in_lab`
- `processed`
- `sent`
- `cancelled`
- `error_pending_assignment`
