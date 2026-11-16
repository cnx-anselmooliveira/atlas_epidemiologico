-- Gold: wrapper fino sobre o seed de população por município do Brasil
-- (ver seeds/seed_populacao_municipio_brasil.csv) — só adiciona
-- gold_generated_at pra entrar no mesmo mecanismo de sync/export da API.

select
    municipality_id,
    municipality_name,
    state_code,
    population,
    population_year,
    source_name,
    current_timestamp() as gold_generated_at
from {{ ref('seed_populacao_municipio_brasil') }}
