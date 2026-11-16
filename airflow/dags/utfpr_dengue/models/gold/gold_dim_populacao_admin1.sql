-- Gold: wrapper fino sobre o seed de população por admin1 (ver
-- seeds/seed_populacao_admin1.csv) — só adiciona gold_generated_at pra
-- entrar no mesmo mecanismo de sync/export da API (ver
-- infra/api/app/gold_sync.py) igual as demais tabelas Gold.

select
    country_iso3,
    admin1_name,
    population,
    population_year,
    source_name,
    current_timestamp() as gold_generated_at
from {{ ref('seed_populacao_admin1') }}
