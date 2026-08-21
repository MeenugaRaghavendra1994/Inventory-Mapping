create table if not exists public.bom_records (
    row_number bigint primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.master_records (
    row_number bigint primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.inventory_records (
    row_number bigint primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.final_inventory_records (
    report_date date not null,
    row_number bigint not null,
    data jsonb not null,
    updated_at timestamptz not null default now(),
    primary key (report_date, row_number)
);

alter table public.bom_records enable row level security;
alter table public.master_records enable row level security;
alter table public.inventory_records enable row level security;
alter table public.final_inventory_records enable row level security;

drop policy if exists "service role can manage bom records" on public.bom_records;
drop policy if exists "service role can manage master records" on public.master_records;
drop policy if exists "service role can manage inventory records" on public.inventory_records;
drop policy if exists "service role can manage final inventory records" on public.final_inventory_records;

create policy "service role can manage bom records"
on public.bom_records for all
to service_role
using (true)
with check (true);

create policy "service role can manage master records"
on public.master_records for all
to service_role
using (true)
with check (true);

create policy "service role can manage inventory records"
on public.inventory_records for all
to service_role
using (true)
with check (true);

create policy "service role can manage final inventory records"
on public.final_inventory_records for all
to service_role
using (true)
with check (true);