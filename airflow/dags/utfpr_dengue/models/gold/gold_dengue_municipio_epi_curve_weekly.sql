-- Gold: curva epidemiológica semanal por MUNICÍPIO (drill-down do mapa
-- estadual — clicar numa UF no front troca pro mapa de município dentro
-- daquele estado). Só Brasil: é a única fonte com granularidade de
-- município (nível de caso em silver_dengue_cases_brasil); as outras
-- fontes nacionais só chegam até nível de UF/depto/província.
-- Grão: UF × município × ano epidemiológico × semana epidemiológica.
-- Fonte Silver: silver_dengue_cases_brasil.

with base as (

    select
        notification_state                     as state_code,
        notification_municipality_id            as municipality_id,
        notification_municipality_name          as municipality_name,
        notification_epi_year                   as year,
        notification_epi_week_number            as epi_week,
        count(*)                                as total_cases
    from {{ ref('silver_dengue_cases_brasil') }}
    where notification_epi_year is not null
      and notification_epi_week_number is not null
      and notification_municipality_id is not null
    group by 1, 2, 3, 4, 5

)

select
    state_code,
    municipality_id,
    municipality_name,
    year,
    epi_week,
    date_add(date(cast(year as int64), 1, 1), interval (epi_week - 1) * 7 day) as epi_week_start_date,
    total_cases,

    -- estável dentro da mesma execução (mesmo valor em todas as linhas) —
    -- usado pelo job de exportação pra saber se a tabela mudou desde a
    -- última cópia local, sem precisar reprocessar o dado inteiro.
    current_timestamp()                                     as gold_generated_at

from base
