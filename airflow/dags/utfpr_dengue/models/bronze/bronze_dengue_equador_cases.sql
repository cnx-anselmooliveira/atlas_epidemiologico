-- Bronze: dengue do Equador, planilha DCSA_DG_2021_2025 (nível de caso,
-- dengue grave).
--
-- Nomes de coluna abaixo são os NOMES REAIS após a sanitização de
-- scripts/carregar_bigquery.py::sanear_nomes_de_coluna, recalculados
-- rodando a própria função contra a lista original de colunas (não um
-- chute): "Cod Prov Domic" -> "Cod_Prov_Domic", "Fec. fallec" ->
-- "Fec_fallec" etc. `Año` mantém o acento (precisa de crase). Todas as
-- colunas chegam como STRING.

select
    to_hex(md5(
        {{ concat_ws('|', ['`Año`', 'Cod_Parroq_Domic', 'Sexo', 'Edad', 'Inicio_de_sintomas', 'SE']) }}
    ))                                       as case_id,

    safe_cast(`Año` as int64)               as notification_year,
    safe_cast(SE as int64)                  as notification_epi_week,

    Institucion                             as institution_name,
    Unidad_Operativa                        as health_unit_name,

    Cod_Prov_Domic                          as province_code,
    Prov_Domic                               as province_name,
    Cod_Canton_Domic                        as canton_code,
    Canton_Domic                            as canton_name,
    Cod_Parroq_Domic                        as parish_code,
    Parroq_Domic                            as parish_name,

    Sexo                                    as patient_sex,
    safe_cast(Edad as int64)                as patient_age,
    Tipo_edad                               as patient_age_unit,
    Autoidentificacion                      as patient_ethnicity,

    {{ parse_date_any('Inicio_de_sintomas') }} as symptom_onset_date,
    Antecedente_viaje                       as travel_history_flag,
    Lugar_Viaje                             as travel_location,
    Laboratorio                             as lab_result,
    Condicion_final                         as final_condition,
    {{ parse_date_any('Fec_fallec') }}      as death_date,
    Diagnostico_final                       as final_diagnosis,
    Confirmado_por                          as confirmed_by

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_equador') }}
where hoja_origem = 'DCSA_DG_2021_2025'
