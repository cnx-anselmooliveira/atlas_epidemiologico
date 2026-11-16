-- Bronze: dengue da Bolívia (PAHO/PLISA), agregado por departamento ×
-- semana epidemiológica. Carregada via `autodetect=True` do BigQuery (não
-- pelo loader "tudo STRING"), então os tipos já vêm inferidos do CSV — os
-- nomes de coluna com espaço/acento abaixo usam crase (nome exato como no
-- CSV original; não confirmado contra o schema real, já que a inferência
-- de nome de coluna do autodetect do BigQuery não foi verificada ao vivo).

select
    safe_cast(`Año` as int64)                            as notification_year,
    safe_cast(`Semana Epidemiológica` as int64)          as notification_epi_week,
    `Departamento`                                        as department_name,

    safe_cast(`Total de Casos` as int64)                  as total_cases,
    safe_cast(`Casos Confirmados` as int64)                as confirmed_cases,
    safe_cast(`Casos sin signos de alarma` as int64)      as cases_without_warning_signs,
    safe_cast(`Casos con signos de alarma` as int64)      as cases_with_warning_signs,
    safe_cast(`Casos con Dengue grave` as int64)          as severe_dengue_cases,
    safe_cast(`Muertes` as int64)                         as deaths

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_bolivia') }}
