-- Gold: distribuição demográfica dos casos de dengue no Brasil.
-- Finalidade: apoiar análises de perfil de risco (sexo × faixa etária) e
-- letalidade por grupo, único país com detalhe de caso rico o bastante
-- para essa quebra.
-- Grão: ano epidemiológico × sexo do paciente × faixa etária.
-- Fonte Silver: silver_dengue_cases_brasil.

with grouped as (

    select
        notification_epi_year          as year,
        patient_sex,
        patient_age_band,
        count(*)                       as case_count,
        countif(is_death)              as death_count
    from {{ ref('silver_dengue_cases_brasil') }}
    where notification_epi_year is not null
    group by 1, 2, 3

)

select
    year,
    patient_sex,
    patient_age_band,
    case_count,
    death_count,

    case when case_count > 0
         then round(100.0 * death_count / case_count, 4)
    end                                                    as case_fatality_rate_pct,

    round(
        100.0 * case_count / nullif(
            sum(case_count) over (partition by year), 0
        ),
        2
    )                                                      as pct_of_year_total_cases,

    current_timestamp()                                   as gold_generated_at

from grouped
