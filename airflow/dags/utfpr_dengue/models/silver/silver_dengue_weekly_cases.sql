-- Silver: fato consolidado de casos de dengue, grão = país × unidade
-- administrativa de nível 1 (UF/departamento/província, quando disponível)
-- × ano epidemiológico × semana epidemiológica.
--
-- É o único grão comum que permite reunir, via UNION ALL, fontes que
-- chegam em nível de caso (Brasil, Colômbia, Peru, Equador-casos) e fontes
-- que já chegam agregadas (Bolívia, Argentina, Equador-agregado, PAHO).
-- Onde uma fonte não permite calcular uma métrica com confiança (ex.
-- confirmed_cases no Brasil/Colômbia, cuja codificação de
-- case_classification/case_type não está documentada nas colunas
-- disponíveis), o campo fica NULL propositalmente em vez de estimado.
--
-- `epi_week_start_date` é uma aproximação (ano epidemiológico + (semana-1)*7
-- dias), usada só para permitir agregações mensais/anuais na Gold — não
-- reproduz a definição exata de semana epidemiológica de cada país
-- (convenções de início de semana variam).

with brasil as (

    select
        'BRA'                           as country_iso3,
        'Brasil'                        as country_name,
        notification_state              as admin1_code,
        notification_state              as admin1_name,
        notification_epi_year,
        notification_epi_week_number    as notification_epi_week,
        count(*)                        as total_cases,
        cast(null as int64)             as confirmed_cases,
        cast(null as int64)             as severe_cases,
        countif(is_death)               as deaths,
        'national'                      as data_source_priority,
        'bronze_dengue_brasil'          as source_model
    from {{ ref('silver_dengue_cases_brasil') }}
    where notification_epi_year is not null
      and notification_epi_week_number is not null
    group by 1, 2, 3, 4, 5, 6

),

-- Complemento do Brasil com PAHO: o SINAN (Base dos Dados) é publicado com
-- meses de defasagem, e a última semana dele costuma vir incompleta (só os
-- primeiros dias notificados). Regra: SINAN vale ATÉ a penúltima semana
-- disponível; da última semana do SINAN em diante, usa o PAHO (nível
-- nacional, sem UF — por isso essas semanas entram no total do país mas
-- não no mapa por estado). Quando o SINAN alcançar o PAHO, o complemento
-- fica vazio sozinho.
brasil_corte as (

    select max(notification_epi_year * 100 + notification_epi_week) as semana_corte
    from brasil

),

brasil_sinan as (

    select b.*
    from brasil b
    cross join brasil_corte c
    where b.notification_epi_year * 100 + b.notification_epi_week < c.semana_corte

),

brasil_paho_semanal as (

    -- o bronze do PAHO traz linhas repetidas por semana (mesmo acumulado);
    -- colapsa antes do lag() pra a diferença semanal não depender da ordem.
    select
        notification_year,
        notification_epi_week,
        max(cumulative_total_cases) as cumulative_total_cases,
        max(severe_dengue_cases)    as severe_dengue_cases,
        max(deaths)                 as deaths
    from {{ ref('bronze_dengue_paho_americas') }}
    where country_or_subregion = 'Brazil'
    group by 1, 2

),

brasil_paho as (

    select
        'BRA'                                                       as country_iso3,
        'Brasil'                                                    as country_name,
        cast(null as string)                                        as admin1_code,
        cast(null as string)                                        as admin1_name,
        p.notification_year                                         as notification_epi_year,
        p.notification_epi_week,
        coalesce(
            p.cumulative_total_cases - lag(p.cumulative_total_cases) over w,
            p.cumulative_total_cases
        )                                                           as total_cases,
        cast(null as int64)                                         as confirmed_cases,
        coalesce(p.severe_dengue_cases - lag(p.severe_dengue_cases) over w, p.severe_dengue_cases)
                                                                    as severe_cases,
        coalesce(p.deaths - lag(p.deaths) over w, p.deaths)         as deaths,
        'paho_fallback'                                             as data_source_priority,
        'bronze_dengue_paho_americas'                               as source_model,
        p.notification_year * 100 + p.notification_epi_week         as chave_semana
    from brasil_paho_semanal p
    window w as (partition by p.notification_year order by p.notification_epi_week)

),

brasil_paho_complemento as (

    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from brasil_paho p
    cross join brasil_corte c
    where p.chave_semana >= c.semana_corte

),

colombia as (

    select
        'COL'                                  as country_iso3,
        'Colômbia'                              as country_name,
        occurrence_department_code             as admin1_code,
        occurrence_department_name             as admin1_name,
        notification_year                      as notification_epi_year,
        notification_epi_week,
        count(*)                               as total_cases,
        cast(null as int64)                    as confirmed_cases,
        countif(case_severity_category = 'Dengue Grave')
                                                as severe_cases,
        countif(death_date is not null)
                                                as deaths,
        'national'                             as data_source_priority,
        'bronze_dengue_colombia'               as source_model
    from {{ ref('bronze_dengue_colombia') }}
    where notification_year is not null
      and notification_epi_week is not null
    group by 1, 2, 3, 4, 5, 6

),

peru as (

    select
        'PER'                                   as country_iso3,
        'Peru'                                   as country_name,
        cast(null as string)                     as admin1_code,
        department_name                          as admin1_name,
        notification_year                        as notification_epi_year,
        notification_epi_week,
        count(*)                                 as total_cases,
        cast(null as int64)                      as confirmed_cases,
        countif(lower(disease_name) like '%grave%')
                                                  as severe_cases,
        cast(null as int64)                      as deaths,
        'national'                                as data_source_priority,
        'bronze_dengue_peru'                      as source_model
    from {{ ref('bronze_dengue_peru') }}
    where lower(disease_name) like '%dengue%'
      and notification_year is not null
      and notification_epi_week is not null
    group by 1, 2, 3, 4, 5, 6

),

argentina_com_codigo_normalizado as (

    -- admin1 da Argentina é província (mesmo nível dos demais países),
    -- não departamento — department_code só é único DENTRO de uma
    -- província (confirmado direto no bronze: o código "007" sozinho
    -- aparece em 13 províncias diferentes), então usar department_name
    -- como admin1_name (como era antes) misturava ~471 departamentos
    -- sujos onde deveria haver as 24 províncias reais.
    --
    -- A fonte bruta às vezes traz province_code/province_name com as
    -- colunas trocadas e o código sem zero à esquerda ("6" em vez de
    -- "06") — normaliza os dois lados antes de casar com o dicionário
    -- (seed_dim_provincia_argentina, ver utfpr_dengue/seeds).
    select
        *,
        case
            when regexp_contains(province_code, r'^\d{1,2}$') then lpad(province_code, 2, '0')
            when regexp_contains(province_name, r'^\d{1,2}$') then lpad(province_name, 2, '0')
            else null
        end as province_code_normalizado
    from {{ ref('bronze_dengue_argentina') }}

),

argentina as (

    -- filtro best-effort: raw source cobre "Dengue y Zika" combinados; sem
    -- confirmar os valores distintos reais de event_name, usa-se
    -- lower(...) like '%dengue%' para excluir eventos de Zika.
    select
        'ARG'                                    as country_iso3,
        'Argentina'                               as country_name,
        a.province_code_normalizado                as admin1_code,
        dim.province_name                          as admin1_name,
        a.notification_year                        as notification_epi_year,
        a.notification_epi_week,
        sum(a.case_count)                          as total_cases,
        cast(null as int64)                        as confirmed_cases,
        cast(null as int64)                        as severe_cases,
        cast(null as int64)                        as deaths,
        'national'                                  as data_source_priority,
        'bronze_dengue_argentina'                   as source_model
    from argentina_com_codigo_normalizado a
    inner join {{ ref('seed_dim_provincia_argentina') }} dim
      on a.province_code_normalizado = dim.province_code
    where lower(a.event_name) like '%dengue%'
      and a.notification_year is not null
      and a.notification_epi_week is not null
    group by 1, 2, 3, 4, 5, 6

),

equador_agg as (

    select
        province_name,
        notification_year,
        notification_epi_week,
        sum(total_cases) as total_cases
    from {{ ref('bronze_dengue_equador_weekly_agg') }}
    where lower(event_name) like '%dengue%'
    group by 1, 2, 3

),

equador_severe as (

    select
        province_name,
        notification_year,
        notification_epi_week,
        count(*)                                            as severe_cases,
        countif(death_date is not null)                     as deaths
    from {{ ref('bronze_dengue_equador_cases') }}
    group by 1, 2, 3

),

equador as (

    select
        'ECU'                                                          as country_iso3,
        'Equador'                                                       as country_name,
        cast(null as string)                                            as admin1_code,
        coalesce(a.province_name, s.province_name)                      as admin1_name,
        coalesce(a.notification_year, s.notification_year)              as notification_epi_year,
        coalesce(a.notification_epi_week, s.notification_epi_week)      as notification_epi_week,
        a.total_cases                                                   as total_cases,
        cast(null as int64)                                             as confirmed_cases,
        s.severe_cases                                                  as severe_cases,
        s.deaths                                                        as deaths,
        'national'                                                      as data_source_priority,
        'bronze_dengue_equador_weekly_agg + bronze_dengue_equador_cases' as source_model
    from equador_agg a
    full outer join equador_severe s
        on a.province_name = s.province_name
        and a.notification_year = s.notification_year
        and a.notification_epi_week = s.notification_epi_week

),

bolivia as (

    select
        'BOL'                             as country_iso3,
        'Bolívia'                          as country_name,
        cast(null as string)               as admin1_code,
        department_name                    as admin1_name,
        notification_year                  as notification_epi_year,
        notification_epi_week,
        total_cases,
        confirmed_cases,
        severe_dengue_cases                as severe_cases,
        deaths,
        'national'                          as data_source_priority,
        'bronze_dengue_bolivia'             as source_model
    from {{ ref('bronze_dengue_bolivia') }}

),

paho_incremental as (

    select
        country_or_subregion,
        notification_year,
        notification_epi_week,
        cumulative_total_cases
            - lag(cumulative_total_cases) over (
                partition by country_or_subregion, notification_year
                order by notification_epi_week
              )                                              as delta_total_cases,
        cumulative_total_cases                               as running_total_cases,
        severe_dengue_cases
            - lag(severe_dengue_cases) over (
                partition by country_or_subregion, notification_year
                order by notification_epi_week
              )                                              as delta_severe_cases,
        severe_dengue_cases                                   as running_severe_cases,
        deaths
            - lag(deaths) over (
                partition by country_or_subregion, notification_year
                order by notification_epi_week
              )                                              as delta_deaths,
        deaths                                                as running_deaths
    from {{ ref('bronze_dengue_paho_americas') }}
    -- exclui países já cobertos por fonte nacional, para não contar em dobro
    where country_or_subregion not in (
        'Brazil', 'Colombia', 'Peru', 'Argentina', 'Ecuador', 'Bolivia (Plurinational State of)', 'Bolivia'
    )

),

paho as (

    select
        cast(null as string)                                          as country_iso3,
        country_or_subregion                                          as country_name,
        cast(null as string)                                          as admin1_code,
        cast(null as string)                                          as admin1_name,
        notification_year                                             as notification_epi_year,
        notification_epi_week,
        coalesce(delta_total_cases, running_total_cases)              as total_cases,
        cast(null as int64)                                           as confirmed_cases,
        coalesce(delta_severe_cases, running_severe_cases)            as severe_cases,
        coalesce(delta_deaths, running_deaths)                        as deaths,
        'paho_fallback'                                                as data_source_priority,
        'bronze_dengue_paho_americas'                                  as source_model
    from paho_incremental

),

unioned as (

    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from brasil_sinan
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from brasil_paho_complemento
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from colombia
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from peru
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from argentina
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from equador
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from bolivia
    union all
    select
        country_iso3, country_name, admin1_code, admin1_name,
        notification_epi_year, notification_epi_week,
        total_cases, confirmed_cases, severe_cases, deaths,
        data_source_priority, source_model
    from paho

)

select
    country_iso3,
    country_name,
    admin1_code,
    admin1_name,
    notification_epi_year,
    notification_epi_week,
    date_add(
        date(cast(notification_epi_year as int64), 1, 1),
        interval (notification_epi_week - 1) * 7 day
    )                                                                   as epi_week_start_date,
    total_cases,
    confirmed_cases,
    severe_cases,
    deaths,
    data_source_priority,
    source_model
from unioned
where notification_epi_year is not null
