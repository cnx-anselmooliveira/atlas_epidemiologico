-- Gold: wrapper fino sobre o seed de população por departamento da
-- Argentina (ver seeds/seed_populacao_departamento_argentina.csv) — só
-- adiciona gold_generated_at pra entrar no mesmo mecanismo de sync/export
-- da API.

select
    province_code,
    department_name,
    population,
    population_year,
    source_name,
    current_timestamp() as gold_generated_at
from {{ ref('seed_populacao_departamento_argentina') }}
