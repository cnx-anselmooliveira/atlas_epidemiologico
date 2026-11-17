-- Bronze: dengue do Equador, planilha DSSA_2021_2024 (agregado semanal por
-- faixa etária/sexo, vigilância geral).
--
-- Nomes de coluna abaixo são os NOMES REAIS após a sanitização aplicada por
-- scripts/carregar_bigquery.py::sanear_nomes_de_coluna (\W -> "_", repetido
-- colapsado) — recalculados rodando a própria função contra a lista original
-- de colunas do arquivo, não um chute: "Unidad operativa" -> "Unidad_operativa",
-- "< 1 H" -> "_1_H", "1 - 4 H" -> "_1_4_H", "65+ H" -> "_65_H" etc. `Año` e
-- `Institución` mantêm o acento (não são \W em regex Unicode) e por isso
-- precisam de crase (não são identificador ASCII válido sem quoting no
-- BigQuery). Todas as colunas chegam como STRING.

select
    safe_cast(`Año` as int64)              as notification_year,
    safe_cast(Semana as int64)             as notification_epi_week,

    `Institución`                          as institution_name,
    Unidad_operativa                       as health_unit_name,
    Unicodigo                              as health_unit_code,
    Zona                                   as zone_code,
    Distrito                               as district_name,
    Cod_Provincia                          as province_code,
    Provincia                              as province_name,
    Cod_Canton                             as canton_code,
    Canton                                 as canton_name,
    Cod_Parroquia                          as parish_code,
    Parroquia                              as parish_name,
    Evento                                 as event_name,

    safe_cast(_1_H as int64)               as cases_age_lt1_male,
    safe_cast(_1_M as int64)               as cases_age_lt1_female,
    safe_cast(_1_4_H as int64)             as cases_age_1_4_male,
    safe_cast(_1_4_M as int64)             as cases_age_1_4_female,
    safe_cast(_5_9_H as int64)             as cases_age_5_9_male,
    safe_cast(_5_9_M as int64)             as cases_age_5_9_female,
    safe_cast(_10_14_H as int64)           as cases_age_10_14_male,
    safe_cast(_10_14_M as int64)           as cases_age_10_14_female,
    safe_cast(_15_19_H as int64)           as cases_age_15_19_male,
    safe_cast(_15_19_M as int64)           as cases_age_15_19_female,
    safe_cast(_20_49_H as int64)           as cases_age_20_49_male,
    safe_cast(_20_49_M as int64)           as cases_age_20_49_female,
    safe_cast(_50_64_H as int64)           as cases_age_50_64_male,
    safe_cast(_50_64_M as int64)           as cases_age_50_64_female,
    safe_cast(_65_H as int64)              as cases_age_65plus_male,
    safe_cast(_65_M as int64)              as cases_age_65plus_female,

    safe_cast(Hombres as int64)            as total_cases_male,
    safe_cast(Mujeres as int64)            as total_cases_female,
    safe_cast(Total as int64)              as total_cases

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_equador') }}
where hoja_origem = 'DSSA_2021_2024'
