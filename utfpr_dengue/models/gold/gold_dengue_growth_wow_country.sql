-- Gold: crescimento semana a semana de casos de dengue por país.
-- Finalidade: identificar aceleração/desaceleração de surtos por país
-- (indicador temporal/de crescimento) para alerta em dashboards.
-- Grão: país × ano epidemiológico × semana epidemiológica.
-- Fonte Silver: silver_dengue_weekly_cases.

with country_weekly as (

    select
        country_iso3,
        country_name,
        notification_epi_year                        as year,
        notification_epi_week                         as epi_week,
        epi_week_start_date,
        sum(total_cases)                              as total_cases
    from {{ ref('silver_dengue_weekly_cases') }}
    group by 1, 2, 3, 4, 5

)

select
    country_iso3,
    country_name,
    year,
    epi_week,
    epi_week_start_date,
    total_cases,

    lag(total_cases) over (
        partition by country_iso3, country_name order by year, epi_week
    )                                                as previous_week_cases,

    round(
        100.0 * (
            total_cases - lag(total_cases) over (
                partition by country_iso3, country_name order by year, epi_week
            )
        ) / nullif(
            lag(total_cases) over (
                partition by country_iso3, country_name order by year, epi_week
            ), 0
        ),
        2
    )                                                as wow_growth_pct,

    round(
        avg(total_cases) over (
            partition by country_iso3, country_name
            order by year, epi_week
            rows between 3 preceding and current row
        ),
        2
    )                                                as rolling_avg_cases_4w,

    current_timestamp()                             as gold_generated_at

from country_weekly
