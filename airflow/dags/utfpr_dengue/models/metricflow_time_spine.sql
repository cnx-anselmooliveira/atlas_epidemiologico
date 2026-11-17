{{
    config(
        materialized='table'
    )
}}

-- Time spine exigida pelo dbt Semantic Layer (MetricFlow) para resolver
-- métricas com granularidade de tempo (ver semantic_models nos modelos
-- gold_*). Cobre um intervalo generoso em torno dos dados do projeto
-- (PAHO/SINAN vão de 2014 até o ano corrente).
select
    date_day
from unnest(
    generate_date_array('2010-01-01', '2030-12-31', interval 1 day)
) as date_day
