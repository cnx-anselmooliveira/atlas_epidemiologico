-- Gold: taxa de incidência semanal de dengue por país (casos por 100 mil
-- habitantes) — equivalente ao gráfico de incidência do
-- info.dengue.mat.br, mas só em nível de país.
--
-- LIMITAÇÃO IMPORTANTE: não existe fonte de população por UF/departamento/
-- província carregada no projeto — só o PAHO/ARBO Portal reporta
-- população, e apenas em nível de país ("Population X 1000"). Por isso
-- este indicador só é calculado em nível de país; para incidência por
-- UF/depto seria necessário carregar uma fonte de população subnacional
-- (ex. IBGE para o Brasil, DANE para a Colômbia, INEI para o Peru) — não
-- inventado aqui.
--
-- Grão: país × ano epidemiológico × semana epidemiológica.
-- Fontes Silver/Bronze: silver_dengue_weekly_cases, bronze_dengue_paho_americas.

with country_weekly as (

    select
        country_iso3,
        country_name,
        notification_epi_year          as year,
        notification_epi_week          as epi_week,
        epi_week_start_date,
        sum(total_cases)               as total_cases
    from {{ ref('silver_dengue_weekly_cases') }}
    group by 1, 2, 3, 4, 5

),

-- crosswalk entre o nome do país usado nas fontes nacionais (português) e
-- o nome em inglês usado pelo PAHO/ARBO Portal, único jeito de casar com a
-- coluna de população. Fontes com fallback PAHO (country_iso3 nulo) já têm
-- country_name igual ao texto do próprio PAHO, não precisam de crosswalk.
country_name_crosswalk as (

    select country_iso3, paho_country_name
    from unnest([
        struct('BRA' as country_iso3, 'Brazil'                            as paho_country_name),
        struct('COL',                 'Colombia'),
        struct('PER',                 'Peru'),
        struct('ARG',                 'Argentina'),
        struct('ECU',                 'Ecuador'),
        struct('BOL',                 'Bolivia (Plurinational State of)'),
        struct('BOL',                 'Bolivia')
    ])

),

population as (

    select
        country_or_subregion,
        notification_year                       as year,
        max(population_thousands)               as population_thousands
    from {{ ref('bronze_dengue_paho_americas') }}
    group by 1, 2

),

joined_with_crosswalk as (

    select
        w.country_iso3,
        w.country_name,
        w.year,
        w.epi_week,
        w.epi_week_start_date,
        w.total_cases,
        coalesce(x.paho_country_name, w.country_name)  as population_join_name
    from country_weekly w
    left join country_name_crosswalk x
        on w.country_iso3 = x.country_iso3

)

select
    cw_result.country_iso3,
    cw_result.country_name,
    cw_result.year,
    cw_result.epi_week,
    cw_result.epi_week_start_date,
    cw_result.total_cases,
    p.population_thousands,

    case
        when p.population_thousands is not null and p.population_thousands > 0
        then round(cw_result.total_cases / p.population_thousands * 100.0, 4)
    end                                          as incidence_per_100k,

    current_timestamp()                         as gold_generated_at

from joined_with_crosswalk cw_result
left join population p
    on p.country_or_subregion = cw_result.population_join_name
   and p.year = cw_result.year
