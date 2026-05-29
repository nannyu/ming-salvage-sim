-- Supabase schema for multi-user support
-- Run in Supabase SQL editor. Backend uses service_role (bypasses RLS).

create table if not exists public.profiles (
  user_id uuid primary key,
  email text not null default '',
  role text not null default 'user' check (role in ('user', 'admin')),
  status text not null default 'active' check (status in ('active', 'disabled', 'deleted')),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_progress_records (
  user_id uuid primary key,
  year int not null default 0,
  period int not null default 0,
  turn int not null default 0,
  treasury text not null default '',
  metrics jsonb not null default '{}'::jsonb,
  save_count int not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.admin_audit_logs (
  id bigserial primary key,
  actor_user_id uuid not null,
  action text not null,
  target_user_id text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.user_progress_records enable row level security;
alter table public.admin_audit_logs enable row level security;

-- Deny direct client access; all business traffic goes through FastAPI + service_role.
create policy "profiles_no_anon" on public.profiles for all to anon using (false);
create policy "profiles_no_authenticated" on public.profiles for all to authenticated using (false);

create policy "progress_no_anon" on public.user_progress_records for all to anon using (false);
create policy "progress_no_authenticated" on public.user_progress_records for all to authenticated using (false);

create policy "audit_no_anon" on public.admin_audit_logs for all to anon using (false);
create policy "audit_no_authenticated" on public.admin_audit_logs for all to authenticated using (false);

-- Bootstrap first admin (optional one-time):
-- update public.profiles set role = 'admin' where email = 'your@email.com';
