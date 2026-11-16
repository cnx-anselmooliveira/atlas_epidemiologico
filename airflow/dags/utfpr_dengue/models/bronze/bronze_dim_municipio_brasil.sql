-- Bronze: dimensão de municípios do Brasil (para enriquecer bronze_dengue_brasil).
-- Schema confirmado por consulta direta ao arquivo local
-- microdados/brasil_microdados_sinan/br_ms_sinan.duckdb (tabela municipios,
-- 5.571 linhas): id_municipio/id_regiao_saude são INT64, amazonia_legal é
-- INT64 (0/1, não booleano), centroide já vem como texto WKT ("POINT(lon lat)").

select
    safe_cast(id_municipio as int64)               as municipality_id,
    nome                                            as municipality_name,
    sigla_uf                                        as state_code,
    nome_uf                                         as state_name,
    nome_regiao                                     as region_name,
    safe_cast(id_regiao_saude as int64)             as health_region_id,
    nome_regiao_saude                               as health_region_name,
    id_regiao_metropolitana                         as metropolitan_region_id,
    nome_regiao_metropolitana                       as metropolitan_region_name,
    (safe_cast(amazonia_legal as int64) = 1)        as legal_amazon_flag,
    centroide                                       as centroid_wkt

from {{ source('raw_uftpr_microdados', 'raw_uftpr_dim_municipio_brasil') }}
