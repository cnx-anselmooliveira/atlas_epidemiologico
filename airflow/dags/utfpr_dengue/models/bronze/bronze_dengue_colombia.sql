-- Bronze: casos de dengue da Colômbia (SIVIGILA), nível de caso.
-- Fonte já traz `classificacao` (Dengue / Dengue Grave) e `arquivo_origem`
-- como colunas de proveniência adicionadas na ingestão. Todas as colunas
-- chegam como STRING (ver sources.yaml) — datas usam parse_date_any (best
-- effort, formato exato não confirmado contra os dados reais).

select
    to_hex(md5(
        {{ concat_ws('|', ['CONSECUTIVE', 'FEC_NOT', 'COD_MUN_O', 'arquivo_origem']) }}
    ))                                           as case_id,
    safe_cast(CONSECUTIVE as string)             as source_record_id,
    classificacao                                as case_severity_category,
    COD_EVE                                      as event_code,
    Nombre_evento                                as event_name,

    {{ parse_date_any('FEC_NOT') }}               as notification_date,
    safe_cast(SEMANA as int64)                   as notification_epi_week,
    safe_cast(ANO as int64)                      as notification_year,

    safe_cast(EDAD as int64)                     as patient_age,
    UNI_MED                                      as patient_age_unit,
    SEXO                                         as patient_sex,
    {{ parse_date_any('FECHA_NTO') }}             as patient_birth_date,
    AREA                                         as area_type,

    COD_DPTO_O                                   as occurrence_department_code,
    Departamento_ocurrencia                      as occurrence_department_name,
    COD_MUN_O                                    as occurrence_municipality_code,
    Municipio_ocurrencia                         as occurrence_municipality_name,

    COD_DPTO_R                                   as residence_department_code,
    Departamento_residencia                      as residence_department_name,
    COD_MUN_R                                    as residence_municipality_code,
    Municipio_residencia                         as residence_municipality_name,

    {{ parse_date_any('INI_SIN') }}               as symptom_onset_date,
    {{ parse_date_any('FEC_CON') }}               as consultation_date,
    TIP_CAS                                      as case_type_code,

    PAC_HOS                                      as hospitalized_flag,
    {{ parse_date_any('FEC_HOS') }}               as hospitalization_date,

    CON_FIN                                      as final_condition,
    {{ parse_date_any('FEC_DEF') }}               as death_date,

    Estado_final_de_caso                         as final_case_status_code,
    nom_est_f_caso                               as final_case_status_desc,

    arquivo_origem                               as source_file_name

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_colombia') }}
