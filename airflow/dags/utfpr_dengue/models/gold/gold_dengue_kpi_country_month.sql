-- Gold: indicadores mensais de dengue por país.
-- Finalidade: séries temporais mensais por país para dashboards/BI.
-- Grão: país × ano × mês (mês derivado de epi_week_start_date, aproximado).
-- Fonte Silver: silver_dengue_weekly_cases.

select
    country_iso3,
    country_name,
    notification_epi_year                                  as year,
    extract(month from epi_week_start_date)                as month,
    date_trunc(epi_week_start_date, month)                  as month_ref,

    sum(total_cases)                                        as total_cases,
    sum(confirmed_cases)                                    as total_confirmed_cases,
    sum(severe_cases)                                       as total_severe_cases,
    sum(deaths)                                              as total_deaths,
    count(distinct notification_epi_week)                    as distinct_weeks_reported,

    case when sum(total_cases) > 0
         then round(100.0 * sum(deaths) / sum(total_cases), 4)
    end                                                       as case_fatality_rate_pct,

    current_timestamp()                                       as gold_generated_at

from {{ ref('silver_dengue_weekly_cases') }}
group by 1, 2, 3, 4, 5
