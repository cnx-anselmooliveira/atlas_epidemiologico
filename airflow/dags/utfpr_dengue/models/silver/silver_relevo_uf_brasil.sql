-- Relevo por UF: elevação e declividade médias do Copernicus DEM (polígonos ADM2 do
-- geoBoundaries), ponderadas pela área de cada polígono.
--
-- O region_id do geoBoundaries não casa com o código do IBGE, então cada polígono
-- recebe a UF por cruzamento espacial com os centroides dos municípios do IBGE:
--   1. a UF mais frequente entre os centroides contidos no polígono;
--   2. sem centroide contido, a UF do centroide mais próximo do centro do polígono.
-- municipios_casados conta os polígonos resolvidos pela regra 1 (taxa_casamento).

{{ config(materialized='table') }}

with dem as (
    select
        region_id,
        geometry,
        st_area(geometry) as area_m2,
        mean_elevation,
        mean_slope
    from {{ source('raw_uftpr_microdados', 'raw_uftpr_geospatial_copernicus_dem_regions') }}
    where country_iso3 = 'BRA' and adm_level = 'ADM2'
),

municipios as (
    select state_code as uf, st_geogfromtext(centroid_wkt) as centroide
    from {{ ref('silver_dim_municipio_brasil') }}
    where centroid_wkt is not null
),

por_contencao as (
    select region_id, uf
    from (
        select d.region_id, m.uf, count(*) as n
        from dem as d
        inner join municipios as m on st_contains(d.geometry, m.centroide)
        group by d.region_id, m.uf
    )
    where true
    qualify row_number() over (partition by region_id order by n desc, uf) = 1
),

por_proximidade as (
    select d.region_id, m.uf
    from dem as d
    cross join municipios as m
    where d.region_id not in (select region_id from por_contencao)
    qualify row_number() over (
        partition by d.region_id order by st_distance(st_centroid(d.geometry), m.centroide)
    ) = 1
),

atribuido as (
    select
        d.*,
        coalesce(c.uf, p.uf) as uf,
        c.uf is not null as casado
    from dem as d
    left join por_contencao as c using (region_id)
    left join por_proximidade as p using (region_id)
)

select
    uf,
    sum(mean_elevation * area_m2) / sum(area_m2) as mean_elevation_m,
    sum(mean_slope * area_m2) / sum(area_m2) as mean_slope_deg,
    count(*) as municipios_dem,
    countif(casado) as municipios_casados,
    round(countif(casado) / count(*), 4) as taxa_casamento
from atribuido
group by uf
