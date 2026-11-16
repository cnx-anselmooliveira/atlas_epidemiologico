-- Gold: ranking de unidades administrativas (UF/departamento/província)
-- por volume de casos de dengue, dentro de cada país e ano.
-- Finalidade: apontar as regiões mais afetadas por país/ano e identificar
-- hotspots recorrentes (indicador de recorrência).
-- Grão: país × ano epidemiológico × unidade administrativa nível 1.
-- Fonte Silver: silver_dengue_weekly_cases (só linhas com admin1_name
-- preenchido; PAHO fica de fora por não ter granularidade subnacional).

with yearly_admin1 as (

    select
        country_iso3,
        country_name,
        notification_epi_year                as year,
        admin1_name,
        sum(total_cases)                      as total_cases
    from {{ ref('silver_dengue_weekly_cases') }}
    where admin1_name is not null
    group by 1, 2, 3, 4

),

ranked as (

    select
        country_iso3,
        country_name,
        year,
        admin1_name,
        total_cases,
        dense_rank() over (
            partition by country_iso3, country_name, year
            order by total_cases desc
        )                                                       as rank_in_country_year,
        round(
            100.0 * total_cases / nullif(
                sum(total_cases) over (partition by country_iso3, country_name, year), 0
            ),
            2
        )                                                       as share_of_country_total_pct
    from yearly_admin1

)

select
    r.country_iso3,
    r.country_name,
    r.year,
    r.admin1_name,
    r.total_cases,
    r.rank_in_country_year,
    r.share_of_country_total_pct,

    -- hotspot recorrente: esteve entre os 5 mais afetados do país também
    -- no ano anterior
    (
        r.rank_in_country_year <= 5
        and lag(r.rank_in_country_year) over (
            partition by r.country_iso3, r.country_name, r.admin1_name
            order by r.year
        ) <= 5
    )                                                              as is_recurrent_top5_hotspot,

    current_timestamp()                                           as gold_generated_at

from ranked r
