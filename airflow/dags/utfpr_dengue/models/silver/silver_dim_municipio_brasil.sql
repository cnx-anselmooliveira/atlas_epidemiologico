-- Silver: dimensão de municípios do Brasil, pass-through padronizado da Bronze.

select
    municipality_id,
    municipality_name,
    state_code,
    state_name,
    region_name,
    health_region_id,
    health_region_name,
    metropolitan_region_id,
    metropolitan_region_name,
    legal_amazon_flag,
    centroid_wkt

from {{ ref('bronze_dim_municipio_brasil') }}
