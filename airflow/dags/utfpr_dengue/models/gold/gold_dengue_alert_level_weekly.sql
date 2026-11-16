-- Gold: nível de alerta semanal por local (equivalente simplificado às
-- faixas verde/amarelo/laranja/vermelho do info.dengue.mat.br).
--
-- IMPORTANTE — isto NÃO é o MEM (Moving Epidemic Method) oficial usado pelo
-- InfoDengue, que ajusta uma curva log-normal/harmônica por temporada. Aqui
-- os limiares são os percentis aproximados 50/75/90 (APPROX_QUANTILES) do
-- histórico de semanas anteriores (mesmo local, todas as semanas com
-- period_key menor que a atual), um proxy simples: >p90 = 'red' (atividade
-- alta/possível epidemia), >p75 e <=p90 = 'orange' (alerta alto), >p50 e
-- <=p75 = 'yellow' (alerta), <=p50 = 'green' (atividade baixa/esperada).
-- Locais com menos de `min_history_weeks` semanas de histórico anterior
-- ficam com alert_level = 'insufficient_history'.
--
-- BigQuery não aceita subquery correlacionada com desigualdade
-- (period_key < w.period_key) referenciando outra tabela — precisa virar
-- um JOIN "de-correlacionado" (aqui, LEFT JOIN por país/local + filtro de
-- desigualdade na condição do JOIN, agregando com GROUP BY).
--
-- Finalidade: sinalizar semanas de atividade anômala por local para
-- dashboards/alerta.
-- Grão: país × unidade administrativa nível 1 × ano epidemiológico ×
-- semana epidemiológica. Fonte Silver: silver_dengue_weekly_cases.

{% set min_history_weeks = 12 %}

with weekly as (

    select
        country_iso3,
        country_name,
        admin1_name,
        notification_epi_year          as year,
        notification_epi_week          as epi_week,
        epi_week_start_date,
        (notification_epi_year * 100 + notification_epi_week)  as period_key,
        sum(total_cases)               as total_cases
    from {{ ref('silver_dengue_weekly_cases') }}
    where admin1_name is not null
    group by 1, 2, 3, 4, 5, 6, 7

),

history_joined as (

    select
        w.country_iso3,
        w.country_name,
        w.admin1_name,
        w.year,
        w.epi_week,
        w.epi_week_start_date,
        w.total_cases,
        h.total_cases as historical_case_count
    from weekly w
    left join weekly h
        on h.country_iso3 = w.country_iso3
       and h.admin1_name = w.admin1_name
       and h.period_key < w.period_key

),

thresholds as (

    select
        country_iso3,
        country_name,
        admin1_name,
        year,
        epi_week,
        epi_week_start_date,
        -- total_cases é igual pra todas as linhas do grupo (repetido pelo
        -- JOIN), então qualquer agregado determinístico serve — usa-se MAX.
        max(total_cases)                                        as total_cases,
        -- count(historical_case_count) ignora NULL (sem histórico ainda),
        -- ao contrário de count(*).
        count(historical_case_count)                            as history_weeks_available,
        approx_quantiles(historical_case_count, 100)[offset(50)] as historical_p50_cases,
        approx_quantiles(historical_case_count, 100)[offset(75)] as historical_p75_cases,
        approx_quantiles(historical_case_count, 100)[offset(90)] as historical_p90_cases
    from history_joined
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
    history_weeks_available,
    round(historical_p50_cases, 2)     as historical_p50_cases,
    round(historical_p75_cases, 2)     as historical_p75_cases,
    round(historical_p90_cases, 2)     as historical_p90_cases,

    case
        when history_weeks_available < {{ min_history_weeks }} then 'insufficient_history'
        when total_cases > historical_p90_cases then 'red'
        when total_cases > historical_p75_cases then 'orange'
        when total_cases > historical_p50_cases then 'yellow'
        else 'green'
    end                                 as alert_level,

    current_timestamp()                as gold_generated_at

from thresholds
