-- VÍA VIVA · tablas públicas en Supabase (PostgreSQL). Se pegan UNA vez en el editor SQL del proyecto de Supabase.
-- Solo reciben lo que viaviva/sincronizacion.py deja salir (lista blanca): eventos sin velocidad, vehículo, foto ni
-- etiqueta en texto, y probabilidad de riesgo por tramo sin variables ni datos de la Alcaldía.
-- SQLite en la Pi sigue siendo la fuente de verdad; esto es una copia para consulta.
--
-- Seguridad: RLS activado. Cualquiera puede LEER (es la capa pública); nadie puede escribir con la clave pública.
-- La Pi escribe con la clave SECRETA del proyecto (salta RLS), guardada solo en el .env de la Pi como SUPABASE_CLAVE.

create table if not exists eventos_publicos (
    id_origen       text primary key,          -- "<id_nodo>|<ts_utc>": evita duplicados en los reintentos
    ts_utc          timestamptz not null,
    lat             double precision not null, -- redondeada a 5 decimales (~1 m)
    lon             double precision not null,
    clase           text not null,
    etiquetado      boolean not null default false,
    id_tramo        integer,
    geohash7        text,
    origen          text not null,
    modelo_version  text,
    recibido        timestamptz not null default now()
);

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

alter table eventos_publicos enable row level security;
alter table riesgo_publico enable row level security;
drop policy if exists "lectura publica" on eventos_publicos;
drop policy if exists "lectura publica" on riesgo_publico;
create policy "lectura publica" on eventos_publicos for select using (true);
create policy "lectura publica" on riesgo_publico for select using (true);
-- Sin políticas de insert/update/delete: con la clave pública no se puede escribir.
