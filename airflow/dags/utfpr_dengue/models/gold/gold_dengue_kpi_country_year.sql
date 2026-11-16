-- Gold: indicadores anuais de dengue por país.
-- Finalidade: visão executiva ano a ano por país (totais, letalidade,
-- crescimento) para BI/dashboards.
-- Grão: país × ano epidemiológico.
-- Fontes Silver: silver_dengue_weekly_cases, silver_dim_country.

with yearly as (

    select
        country_iso3,
        country_name,
        notification_epi_year                          as year,
        sum(total_cases)                                as total_cases,
        sum(confirmed_cases)                            as total_confirmed_cases,
        sum(severe_cases)                               as total_severe_cases,
        sum(deaths)                                     as total_deaths,
        count(distinct notification_epi_week)           as distinct_weeks_reported,
        count(distinct admin1_name)                     as distinct_admin1_reporting,
        max(data_source_priority)                       as data_source_priority
    from {{ ref('silver_dengue_weekly_cases') }}
    group by 1, 2, 3

)

select
    y.country_iso3,
    y.country_name,
    y.year,
    y.total_cases,
    y.total_confirmed_cases,
    y.total_severe_cases,
    y.total_deaths,
    y.distinct_weeks_reported,
    y.distinct_admin1_reporting,
    y.data_source_priority,
    d.source_status,
    d.primary_source_name,

    case when y.total_cases > 0
         then round(100.0 * y.total_deaths / y.total_cases, 4)
    end                                                 as case_fatality_rate_pct,
    case when y.total_cases > 0
         then round(100.0 * y.total_severe_cases / y.total_cases, 4)
    end                                                 as pct_severe_cases,
    case when y.total_cases > 0
         then round(100.0 * y.total_confirmed_cases / y.total_cases, 4)
    end                                                 as pct_confirmed_cases,
    case when y.distinct_weeks_reported > 0
         then round(y.total_cases * 1.0 / y.distinct_weeks_reported, 2)
    end                                                 as avg_weekly_cases,

    round(
        100.0 * (
            y.total_cases - lag(y.total_cases) over (
                partition by y.country_iso3 order by y.year
            )
        ) / nullif(
            lag(y.total_cases) over (partition by y.country_iso3 order by y.year), 0
        ),
        2
    )                                                   as yoy_growth_pct,

    current_timestamp()                                as gold_generated_at

from yearly y
left join {{ ref('silver_dim_country') }} d
    on y.country_iso3 = d.country_iso3
