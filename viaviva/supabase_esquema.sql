-- VÍA VIVA · base en línea (Supabase / PostgreSQL). Se pega UNA vez en el editor SQL del proyecto (pasos en docs/NUBE.md).
-- SQLite (Pi o PC) es la fuente de verdad: aquí llega una COPIA de eventos, huecos (eventos agrupados con su estado) y
-- riesgo por tramo, con lista blanca de columnas (viaviva/sincronizacion.py). Nada de fotos, video, trayectorias, nombres
-- de quién manejaba ni datos crudos de la Alcaldía.
--
-- Acceso (RLS):
--   * Sin sesión: NADA (la clave pública/anon no lee ni escribe).
--   * Con sesión y perfil: editor (equipo), alcaldia y docente LEEN todo.
--   * Solo editor: pide cambios de estado (cambios_remotos); la Pi los aplica en SQLite y vuelve a subir el hueco.
--   * La Pi escribe con la clave de servicio (salta RLS), guardada solo en su .env. Nunca en la página.

-- ------------------------------------------------------------------ perfiles (rol de cada usuario de Supabase Auth)
create table if not exists perfiles (
    usuario_id  uuid primary key references auth.users (id) on delete cascade,
    nombre      text,
    rol         text not null check (rol in ('editor', 'alcaldia', 'docente'))
);
alter table perfiles enable row level security;

create or replace function public.rol_actual() returns text
language sql stable security definer set search_path = public as
$$ select rol from perfiles where usuario_id = auth.uid() $$;

drop policy if exists "ver mi perfil" on perfiles;
create policy "ver mi perfil" on perfiles for select using (usuario_id = auth.uid());

-- ------------------------------------------------------------------ datos sincronizados desde la Pi / el PC
create table if not exists eventos_publicos (
    id_origen       text primary key,          -- "<id_nodo>|<ts_utc>": idempotente en los reintentos
    ts_utc          timestamptz not null,
    lat             double precision not null, -- 5 decimales (~1 m)
    lon             double precision not null,
    clase           text not null,
    etiquetado      boolean not null default false,
    id_tramo        integer,
    geohash7        text,
    origen          text not null,
    modelo_version  text,
    recibido        timestamptz not null default now()
);

create table if not exists huecos_publicos (
    id_origen       text primary key,          -- "<instancia>|<id_hueco>"
    instancia       text not null,             -- qué base lo tiene (pi-01, phyphox-pc…)
    id_local        integer not null,
    lat             double precision not null,
    lon             double precision not null,
    clase           text not null,
    n_detecciones   integer not null,
    primera_ts      timestamptz not null,
    ultima_ts       timestamptz not null,
    estado          text not null check (estado in ('detectado', 'verificado', 'reparado', 'descartado')),
    severidad       text check (severidad in ('baja', 'media', 'alta')),
    ts_estado       timestamptz,
    id_tramo        integer,
    geohash7        text,
    recibido        timestamptz not null default now()
);
create index if not exists huecos_publicos_estado on huecos_publicos (estado);

create table if not exists riesgo_publico (
    id_origen       text primary key,          -- "<modelo>|<versión>|<fecha>|<id_tramo>"
    id_tramo        integer not null,
    modelo          text not null,
    version_modelo  text not null,
    fecha_calculo   timestamptz not null,
    probabilidad    real not null check (probabilidad between 0 and 1),
    rango           integer,
    recibido        timestamptz not null default now()
);
create index if not exists riesgo_publico_corrida on riesgo_publico (modelo, version_modelo, fecha_calculo);

-- Pedidos de cambio de estado hechos en el tablero en línea (los aplica la Pi)
create table if not exists cambios_remotos (
    id          bigint generated always as identity primary key,
    id_origen   text not null references huecos_publicos (id_origen),
    instancia   text not null,
    id_local    integer not null,
    estado      text not null check (estado in ('detectado', 'verificado', 'reparado', 'descartado')),
    nota        text check (char_length(nota) <= 300),
    autor       text not null default (auth.jwt() ->> 'email'),
    creado      timestamptz not null default now(),
    origen      text not null default 'web' check (origen in ('web', 'csv')),
    aplicado    boolean not null default false,
    resultado   text
);

alter table eventos_publicos enable row level security;
alter table huecos_publicos enable row level security;
alter table riesgo_publico enable row level security;
alter table cambios_remotos enable row level security;

drop policy if exists "leer con rol" on eventos_publicos;
drop policy if exists "leer con rol" on huecos_publicos;
drop policy if exists "leer con rol" on riesgo_publico;
drop policy if exists "leer con rol" on cambios_remotos;
drop policy if exists "editor pide cambios" on cambios_remotos;
create policy "leer con rol" on eventos_publicos for select to authenticated using (rol_actual() is not null);
create policy "leer con rol" on huecos_publicos for select to authenticated using (rol_actual() is not null);
create policy "leer con rol" on riesgo_publico for select to authenticated using (rol_actual() is not null);
create policy "leer con rol" on cambios_remotos for select to authenticated using (rol_actual() is not null);
create policy "editor pide cambios" on cambios_remotos for insert to authenticated
    with check (rol_actual() = 'editor' and aplicado = false and autor = (auth.jwt() ->> 'email'));
-- Sin políticas de update/delete para nadie con sesión: solo la Pi (clave de servicio) marca 'aplicado'.

-- Vista de la última corrida de riesgo (la usa el tablero en línea)
create or replace view riesgo_ultimo with (security_invoker = true) as
select r.* from riesgo_publico r
join (select modelo, version_modelo, fecha_calculo from riesgo_publico
      order by fecha_calculo desc, modelo limit 1) u using (modelo, version_modelo, fecha_calculo);
