-- Bronze: casos de dengue do Brasil (SINAN), nível de caso.
-- Fonte não expõe identificador de caso nativo (base anonimizada) — geramos
-- uma chave substituta apenas para deduplicação/idempotência. Única tabela
-- raw com tipos nativos preservados (CTAS de uma tabela BigQuery já
-- tipada) — mesmo assim usamos safe_cast por segurança.

select
    to_hex(md5(
        {{ concat_ws('|', [
            'data_notificacao',
            'id_municipio_notificacao',
            'id_agravo',
            'ano_nascimento_paciente',
            'sexo_paciente',
            'data_primeiros_sintomas'
        ]) }}
    ))                                                  as case_id,

    -- notification
    safe_cast(ano as int64)                            as notification_year,
    tipo_notificacao                                   as notification_type,
    id_agravo                                          as disease_code,
    safe_cast(data_notificacao as date)                 as notification_date,
    semana_notificacao                                 as notification_epi_week,
    sigla_uf_notificacao                               as notification_state,
    safe_cast(id_municipio_notificacao as int64)        as notification_municipality_id,

    -- symptoms
    safe_cast(data_primeiros_sintomas as date)          as symptom_onset_date,
    semana_sintomas                                    as symptom_onset_epi_week,

    -- patient
    pais_residencia                                    as patient_country_residence,
    sigla_uf_residencia                                 as patient_state_residence,
    safe_cast(id_municipio_residencia as int64)         as patient_municipality_residence_id,
    safe_cast(ano_nascimento_paciente as int64)         as patient_birth_year,
    safe_cast(idade_paciente as int64)                  as patient_age,
    sexo_paciente                                       as patient_sex,
    raca_cor_paciente                                   as patient_race,
    escolaridade_paciente                                as patient_education_level,
    gestante_paciente                                   as patient_pregnancy_status,

    -- hospitalization
    internacao                                          as hospitalized_flag,
    safe_cast(data_internacao as date)                  as hospitalization_date,

    -- classification / lab
    classificacao_final                                 as case_classification,
    criterio_confirmacao                                as confirmation_criteria,
    caso_fhd                                            as severe_dengue_flag,
    caso_autoctone                                      as autochthonous_case_flag,
    sorotipo                                            as dengue_serotype,

    -- infection location
    pais_infeccao                                       as infection_country,
    sigla_uf_infeccao                                   as infection_state,
    safe_cast(id_municipio_infeccao as int64)           as infection_municipality_id,

    -- outcome
    evolucao_caso                                       as case_outcome,
    safe_cast(data_obito as date)                       as death_date,
    safe_cast(data_encerramento as date)                as case_closure_date,

    -- audit
    tipo_sistema                                        as source_system_type,
    safe_cast(data_digitacao as date)                   as data_entry_date

from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_brasil') }}
