-- Gold: curva epidemiológica semanal (equivalente ao gráfico principal do
-- info.dengue.mat.br — "casos notificados por semana", com linha de
-- tendência e comparação com a mesma semana do ano anterior).
-- Finalidade: alimentar o gráfico de série temporal por local (o mais usado
-- em dashboards de vigilância).
-- Grão: país × unidade administrativa nível 1 (quando disponível) × ano
-- epidemiológico × semana epidemiológica.
-- Fonte Silver: silver_dengue_weekly_cases.

with base as (

    select
        country_iso3,
        country_name,
        admin1_name,
        notification_epi_year          as year,
        notification_epi_week          as epi_week,
        epi_week_start_date,
        sum(total_cases)               as total_cases
    from {{ ref('silver_dengue_weekly_cases') }}
    group by 1, 2, 3, 4, 5, 6

)

select
    country_iso3,
    country_name,
    admin1_name,
    year,
    epi_week,
    epi_week_start_date,
    total_cases,

    round(
        avg(total_cases) over (
            partition by country_iso3, country_name, admin1_name
            order by year, epi_week
            rows between 2 preceding and current row
        ),
        2
    )                                                      as moving_avg_cases_3w,

    lag(total_cases, 1) over (
        partition by country_iso3, country_name, admin1_name
        order by year, epi_week
    )                                                       as previous_week_cases,

    lag(total_cases) over (
        partition by country_iso3, country_name, admin1_name, epi_week
        order by year
    )                                                       as same_week_previous_year_cases,

    -- estável dentro da mesma execução (mesmo valor em todas as linhas) —
    -- usado pelo job de exportação pra saber se a tabela mudou desde a
    -- última cópia local, sem precisar reprocessar o dado inteiro.
    current_timestamp()                                     as gold_generated_at

from base
