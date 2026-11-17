-- Gold para os modelos de previsão: casos prováveis de dengue por UF de residência e
-- semana epidemiológica do início dos sintomas (SINAN apenas, sem complemento da OPAS).
-- Série regular: 27 UFs × todas as semanas entre a primeira e a última do período,
-- semanas sem notificação com zero. Traz população do ano epidemiológico, incidência
-- por 100 mil habitantes e relevo da UF como covariáveis estáticas.

{{ config(materialized='table', cluster_by=['uf']) }}

-- A série começa no ano epidemiológico 2000, primeiro ano com população no seed
-- (exclui os poucos casos com início dos sintomas no fim de dezembro de 1999).
with contagens as (
    select * from {{ ref('silver_dengue_casos_uf_semana_brasil') }}
    where {{ epi_year('week_start') }} >= {{ var('gold_first_epi_year', 2000) }}
),

periodo as (
    select min(week_start) as inicio, max(week_start) as fim from contagens
),

ufs as (
    select distinct uf from contagens
),

calendario as (
    select ufs.uf, week_start
    from ufs
    cross join periodo
    cross join unnest(generate_date_array(periodo.inicio, periodo.fim, interval 7 day)) as week_start
),

serie as (
    select
        cal.uf,
        cal.week_start,
        {{ epi_year('cal.week_start') }} as epi_year,
        {{ epi_week('cal.week_start') }} as epi_week,
        coalesce(c.notified_cases, 0) as notified_cases,
        coalesce(c.probable_cases, 0) as probable_cases,
        coalesce(c.discarded_cases, 0) as discarded_cases,
        coalesce(c.confirmed_cases, 0) as confirmed_cases,
        coalesce(c.alarm_cases, 0) as alarm_cases,
        coalesce(c.severe_cases, 0) as severe_cases,
        coalesce(c.inconclusive_cases, 0) as inconclusive_cases,
        coalesce(c.investigation_cases, 0) as investigation_cases,
        coalesce(c.other_cases, 0) as other_cases,
        coalesce(c.deaths, 0) as deaths,
        coalesce(c.date_fallback_cases, 0) as date_fallback_cases,
        coalesce(c.place_fallback_cases, 0) as place_fallback_cases
    from calendario as cal
    left join contagens as c
        on c.uf = cal.uf and c.week_start = cal.week_start
)

select
    s.*,
    p.population,
    p.year as population_year,
    p.origin as population_origin,
    s.probable_cases / p.population * 100000 as incidence,
    r.mean_elevation_m,
    r.mean_slope_deg,
    current_timestamp() as gold_generated_at
from serie as s
left join {{ ref('silver_populacao_uf_anual') }} as p
    on p.uf = s.uf and p.year = s.epi_year
left join {{ ref('silver_relevo_uf_brasil') }} as r
    on r.uf = s.uf
