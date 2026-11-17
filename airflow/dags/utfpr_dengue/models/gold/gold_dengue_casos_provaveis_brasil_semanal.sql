-- Gold nacional: casos prováveis de dengue no Brasil por semana epidemiológica do início dos
-- sintomas, soma das 27 UFs de gold_dengue_casos_provaveis_uf_semanal. Mesma série regular
-- (todas as semanas do período), com a população do Brasil no ano epidemiológico (soma das
-- UFs) e a incidência por 100 mil habitantes. Fonte da série histórica nacional do site.

{{ config(materialized='table') }}

select
    week_start,
    any_value(epi_year) as epi_year,
    any_value(epi_week) as epi_week,
    count(*) as ufs,
    sum(notified_cases) as notified_cases,
    sum(probable_cases) as probable_cases,
    sum(discarded_cases) as discarded_cases,
    sum(confirmed_cases) as confirmed_cases,
    sum(alarm_cases) as alarm_cases,
    sum(severe_cases) as severe_cases,
    sum(inconclusive_cases) as inconclusive_cases,
    sum(investigation_cases) as investigation_cases,
    sum(other_cases) as other_cases,
    sum(deaths) as deaths,
    sum(date_fallback_cases) as date_fallback_cases,
    sum(place_fallback_cases) as place_fallback_cases,
    sum(population) as population,
    max(population_year) as population_year,
    sum(probable_cases) / sum(population) * 100000 as incidence,
    current_timestamp() as gold_generated_at
from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
group by week_start
