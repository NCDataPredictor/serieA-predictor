-- NCData Predictor · cuentas de usuario (26-nov-2026)
-- Pégalo en Supabase → SQL Editor → New query → Run. Se puede correr más de una vez.
-- Una fila por usuario y clave: la clave es la de localStorage de cada liga (sap-mine, epl-combis, nbap-mine,
-- ncdp-rend-serie-a…) y el valor su JSON. Solo el dueño ve y cambia sus filas (RLS).

create table if not exists public.ncdp_datos (
  user_id     uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  clave       text        not null check (clave ~ '^[a-z0-9-]{1,40}$'),
  valor       jsonb       not null check (pg_column_size(valor) < 1000000),
  actualizado timestamptz not null default now(),
  primary key (user_id, clave)
);

alter table public.ncdp_datos enable row level security;

drop policy if exists "ncdp: leer lo propio" on public.ncdp_datos;
drop policy if exists "ncdp: crear lo propio" on public.ncdp_datos;
drop policy if exists "ncdp: cambiar lo propio" on public.ncdp_datos;
drop policy if exists "ncdp: borrar lo propio" on public.ncdp_datos;
create policy "ncdp: leer lo propio"    on public.ncdp_datos for select to authenticated using ((select auth.uid()) = user_id);
create policy "ncdp: crear lo propio"   on public.ncdp_datos for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "ncdp: cambiar lo propio" on public.ncdp_datos for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "ncdp: borrar lo propio"  on public.ncdp_datos for delete to authenticated using ((select auth.uid()) = user_id);

-- "actualizado" lo pone siempre el servidor: así cada navegador sabe si otro cambió algo desde su última sincronización.
create or replace function public.ncdp_tocar() returns trigger language plpgsql set search_path = '' as $$
begin new.actualizado := now(); return new; end $$;
drop trigger if exists ncdp_tocar on public.ncdp_datos;
create trigger ncdp_tocar before insert or update on public.ncdp_datos for each row execute function public.ncdp_tocar();
