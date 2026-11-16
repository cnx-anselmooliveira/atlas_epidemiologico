-- Conferência de totais de casos prováveis em duas etapas:
--   1. silver de casos (não descartados, com data de notificação e alguma UF)
--      = soma da silver agregada por UF e semana;
--   2. silver agregada a partir do ano epidemiológico inicial = soma da gold.
with silver as (
    select countif({{ sinan_classificacao('case_classification') }} != 'descartado') as n
    from {{ ref('silver_dengue_cases_brasil') }}
    where notification_date is not null
      and coalesce(patient_state_residence, notification_state) is not null
),
agregada as (
    select
        sum(probable_cases) as n,
        sum(if({{ epi_year('week_start') }} >= {{ var('gold_first_epi_year', 2000) }}, probable_cases, 0)) as n_periodo
    from {{ ref('silver_dengue_casos_uf_semana_brasil') }}
),
gold as (
    select sum(probable_cases) as n from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
)
select silver.n as silver_n, agregada.n as agregada_n, agregada.n_periodo, gold.n as gold_n
from silver cross join agregada cross join gold
where silver.n != agregada.n or agregada.n_periodo != gold.n
