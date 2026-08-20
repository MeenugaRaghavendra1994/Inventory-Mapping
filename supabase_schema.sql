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

alter table public.bom_records enable row level security;
alter table public.master_records enable row level security;

drop policy if exists "service role can manage bom records" on public.bom_records;
drop policy if exists "service role can manage master records" on public.master_records;

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