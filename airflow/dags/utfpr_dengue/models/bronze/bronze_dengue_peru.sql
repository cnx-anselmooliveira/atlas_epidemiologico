-- Bronze: casos de dengue do Peru (CDC-MINSA / datos abiertos), nível de caso.
-- Todas as colunas chegam como STRING (ver sources.yaml).

select
    to_hex(md5(
        {{ concat_ws('|', ['ano', 'semana', 'ubigeo', 'localcod', 'edad', 'sexo', 'arquivo_origem']) }}
    ))                                        as case_id,

    safe_cast(ano as int64)                   as notification_year,
    safe_cast(semana as int64)                as notification_epi_week,

    departamento                              as department_name,
    provincia                                 as province_name,
    distrito                                  as district_name,
    localidad                                 as locality_name,
    ubigeo                                    as location_ubigeo_code,
    localcod                                  as locality_code,
    diresa                                    as health_directorate_code,

    enfermedad                                as disease_name,
    diagnostic                                as diagnosis_code,

    safe_cast(edad as int64)                  as patient_age,
    tipo_edad                                 as patient_age_unit,
    sexo                                      as patient_sex,

    arquivo_origem                            as source_file_name

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_peru') }}
