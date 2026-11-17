-- Gold: indicadores de qualidade/completude dos dados por país e ano.
-- Finalidade: monitorar completude de reporte (semanas ausentes) e
-- proporção de métricas não disponíveis por fonte, para priorizar
-- validação/enriquecimento das fontes.
-- Grão: país × ano epidemiológico.
-- Fonte Silver: silver_dengue_weekly_cases, silver_dim_country.

with agg as (

    select
        country_iso3,
        country_name,
        notification_epi_year                                   as year,
        count(*)                                                 as row_count,
        count(distinct notification_epi_week)                    as distinct_weeks_reported,
        countif(admin1_name is null)                              as rows_missing_admin1,
        countif(confirmed_cases is null)                          as rows_missing_confirmed,
        countif(severe_cases is null)                             as rows_missing_severe,
        countif(deaths is null)                                   as rows_missing_deaths,
        min(epi_week_start_date)                                   as min_epi_week_start_date,
        max(epi_week_start_date)                                   as max_epi_week_start_date
    from {{ ref('silver_dengue_weekly_cases') }}
    group by 1, 2, 3

)

select
    a.country_iso3,
    a.country_name,
    a.year,
    a.row_count,
    a.distinct_weeks_reported,
    round(100.0 * a.distinct_weeks_reported / 53, 2)        as reporting_completeness_pct,
    round(100.0 * a.rows_missing_admin1 / a.row_count, 2)   as pct_rows_missing_admin1,
    round(100.0 * a.rows_missing_confirmed / a.row_count, 2) as pct_rows_missing_confirmed_cases,
    round(100.0 * a.rows_missing_severe / a.row_count, 2)    as pct_rows_missing_severe_cases,
    round(100.0 * a.rows_missing_deaths / a.row_count, 2)    as pct_rows_missing_deaths,
    a.min_epi_week_start_date,
    a.max_epi_week_start_date,
    d.reporting_frequency_days,
    d.source_status,

    current_timestamp()                                     as gold_generated_at

from agg a
left join {{ ref('silver_dim_country') }} d
    on a.country_iso3 = d.country_iso3
