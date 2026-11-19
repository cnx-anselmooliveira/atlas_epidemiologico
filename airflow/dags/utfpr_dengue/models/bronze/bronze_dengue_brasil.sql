-- Bronze: casos de dengue do Brasil (SINAN), nível de caso.
-- Fonte escolhida por var('sinan_source') (padrão: opendatasus):
--   basedosdados → microdados.raw_uftpr_microdados_brasil (cópia da Base dos Dados, já
--                  harmonizada: UF em sigla, município com 7 dígitos, colunas em português)
--   opendatasus  → <bronze do ambiente>.sinan_dengue_opendatasus (arquivos do OpenDataSUS, nomes originais
--                  do DATASUS, tudo texto), em dois layouts:
--                    2000-2006 SINAN Windows: CON_CLASSI/CON_EVOLUC/CON_CRITER, NU_IDADE "A021",
--                              UF em sigla, município com 7 dígitos, semana "WWAAAA"
--                    2007+     SINAN Net:     CLASSI_FIN/EVOLUCAO/CRITERIO, NU_IDADE_N "4021",
--                              UF em código do IBGE, município com 6 dígitos, semana "AAAAWW"
-- As duas fontes entregam as mesmas colunas e semânticas (contrato do bronze). A chave
-- substituta (md5 das colunas naturais) serve só para deduplicação/idempotência.

{% set fonte = var('sinan_source', 'opendatasus') %}

{% if fonte == 'basedosdados' %}

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

{% else %}

{%- set relacao = source('sinan_opendatasus', 'sinan_dengue_opendatasus') -%}
{%- if execute -%}
    {%- set existentes = adapter.get_columns_in_relation(relacao) | map(attribute='name') | list -%}
{%- else -%}
    {%- set existentes = [] -%}
{%- endif -%}

with origem as (
    select
        s.ano_arquivo,
        {{ sinan_col('NU_ANO', existentes) }}                                   as nu_ano,
        {{ sinan_col('TP_NOT', existentes) }}                                   as tp_not,
        {{ sinan_col('ID_AGRAVO', existentes) }}                                as id_agravo,
        {{ sinan_col('DT_NOTIFIC', existentes) }}                               as dt_notific,
        {{ sinan_col('SEM_NOT', existentes) }}                                  as sem_not,
        {{ sinan_col('SG_UF_NOT', existentes) }}                                as uf_not,
        {{ sinan_col('ID_MUNICIP', existentes) }}                               as mun_not,
        {{ sinan_col('DT_SIN_PRI', existentes) }}                               as dt_sin_pri,
        {{ sinan_col('SEM_PRI', existentes) }}                                  as sem_pri,
        {{ sinan_col('ID_PAIS', existentes) }}                                  as id_pais,
        {{ sinan_col('SG_UF', existentes) }}                                    as uf_res,
        {{ sinan_col('ID_MN_RESI', existentes) }}                               as mun_res,
        {{ sinan_col('ANO_NASC', existentes) }}                                 as ano_nasc,
        {{ sinan_coalesce_col(['NU_IDADE_N', 'NU_IDADE'], existentes) }}        as idade_codificada,
        {{ sinan_col('CS_SEXO', existentes) }}                                  as cs_sexo,
        {{ sinan_col('CS_RACA', existentes) }}                                  as cs_raca,
        {{ sinan_coalesce_col(['CS_ESCOL_N', 'CS_ESCOLAR'], existentes) }}      as escolaridade,
        {{ sinan_col('CS_GESTANT', existentes) }}                               as cs_gestant,
        {{ sinan_col('HOSPITALIZ', existentes) }}                               as hospitaliz,
        {{ sinan_col('DT_INTERNA', existentes) }}                               as dt_interna,
        {{ sinan_coalesce_col(['CLASSI_FIN', 'CON_CLASSI'], existentes) }}      as classi_fin,
        {{ sinan_coalesce_col(['CRITERIO', 'CON_CRITER'], existentes) }}        as criterio,
        {{ sinan_col('CON_FHD', existentes) }}                                  as con_fhd,
        {{ sinan_col('TPAUTOCTO', existentes) }}                                as tpautocto,
        {{ sinan_col('SOROTIPO', existentes) }}                                 as sorotipo,
        {{ sinan_coalesce_col(['COPAISINF', 'CON_INF_PA'], existentes) }}       as pais_inf,
        {{ sinan_coalesce_col(['COUFINF', 'CON_INF_UF'], existentes) }}         as uf_inf,
        {{ sinan_coalesce_col(['COMUNINF', 'CON_INF_MU'], existentes) }}        as mun_inf,
        {{ sinan_coalesce_col(['EVOLUCAO', 'CON_EVOLUC'], existentes) }}        as evolucao,
        {{ sinan_coalesce_col(['DT_OBITO', 'CON_DT_OBI'], existentes) }}        as dt_obito,
        {{ sinan_coalesce_col(['DT_ENCERRA', 'CON_DT_ENC'], existentes) }}      as dt_encerra,
        {{ sinan_col('TP_SISTEMA', existentes) }}                               as tp_sistema,
        {{ sinan_col('DT_DIGITA', existentes) }}                                as dt_digita
    from {{ relacao }} as s
),

municipios as (
    -- código do IBGE com 7 dígitos (com DV) e sem o DV (6 dígitos, usado pelo SINAN Net)
    select municipality_id as mun7, div(municipality_id, 10) as mun6
    from {{ ref('bronze_dim_municipio_brasil') }}
    where municipality_id is not null
),

ufs as (
    -- código do IBGE da UF (2 primeiros dígitos do município) → sigla
    select distinct div(municipality_id, 100000) as uf_codigo, state_code as sigla
    from {{ ref('bronze_dim_municipio_brasil') }}
    where municipality_id is not null
),

traduzido as (
    select
        o.*,
        -- UF: código numérico do IBGE (SINAN Net) → sigla; sigla (SINAN Windows) fica só se for uma
        -- das 27 UFs (o arquivo tem poucos valores corrompidos, ex.: MH, NG; viram nulo)
        coalesce(un.sigla, if(o.uf_not in (select sigla from ufs), o.uf_not, null)) as sg_uf_not,
        coalesce(ur.sigla, if(o.uf_res in (select sigla from ufs), o.uf_res, null)) as sg_uf_res,
        coalesce(ui.sigla, if(o.uf_inf in (select sigla from ufs), o.uf_inf, null)) as sg_uf_inf,
        -- município: 6 dígitos (SINAN Net) → 7 pela dimensão; 7 dígitos (SINAN Windows) fica
        coalesce(mn.mun7, if(length(o.mun_not) = 7, safe_cast(o.mun_not as int64), null)) as id_mun_not,
        coalesce(mr.mun7, if(length(o.mun_res) = 7, safe_cast(o.mun_res as int64), null)) as id_mun_res,
        coalesce(mi.mun7, if(length(o.mun_inf) = 7, safe_cast(o.mun_inf as int64), null)) as id_mun_inf
    from origem as o
    left join ufs as un on regexp_contains(o.uf_not, r'^\d{2}$') and un.uf_codigo = safe_cast(o.uf_not as int64)
    left join ufs as ur on regexp_contains(o.uf_res, r'^\d{2}$') and ur.uf_codigo = safe_cast(o.uf_res as int64)
    left join ufs as ui on regexp_contains(o.uf_inf, r'^\d{2}$') and ui.uf_codigo = safe_cast(o.uf_inf as int64)
    left join municipios as mn on length(o.mun_not) = 6 and mn.mun6 = safe_cast(o.mun_not as int64)
    left join municipios as mr on length(o.mun_res) = 6 and mr.mun6 = safe_cast(o.mun_res as int64)
    left join municipios as mi on length(o.mun_inf) = 6 and mi.mun6 = safe_cast(o.mun_inf as int64)
),

final as (
    select
        -- notification
        -- ano do arquivo, como o `ano` da Base dos Dados (inclui notificações de janeiro seguinte)
        ano_arquivo                                              as notification_year,
        tp_not                                                   as notification_type,
        id_agravo                                                as disease_code,
        {{ parse_date_any('dt_notific') }}                       as notification_date,
        {{ epi_week_text('sem_not', 'ano_arquivo') }}            as notification_epi_week,
        sg_uf_not                                                as notification_state,
        id_mun_not                                               as notification_municipality_id,

        -- symptoms
        {{ parse_date_any('dt_sin_pri') }}                       as symptom_onset_date,
        {{ epi_week_text('sem_pri', 'ano_arquivo') }}            as symptom_onset_epi_week,

        -- patient
        id_pais                                                  as patient_country_residence,
        sg_uf_res                                                as patient_state_residence,
        id_mun_res                                               as patient_municipality_residence_id,
        safe_cast(ano_nasc as int64)                             as patient_birth_year,
        {{ sinan_idade_anos('idade_codificada') }}               as patient_age,
        cs_sexo                                                  as patient_sex,
        cs_raca                                                  as patient_race,
        escolaridade                                             as patient_education_level,
        cs_gestant                                               as patient_pregnancy_status,

        -- hospitalization
        hospitaliz                                               as hospitalized_flag,
        {{ parse_date_any('dt_interna') }}                       as hospitalization_date,

        -- classification / lab
        classi_fin                                               as case_classification,
        criterio                                                 as confirmation_criteria,
        con_fhd                                                  as severe_dengue_flag,
        tpautocto                                                as autochthonous_case_flag,
        sorotipo                                                 as dengue_serotype,

        -- infection location
        pais_inf                                                 as infection_country,
        sg_uf_inf                                                as infection_state,
        id_mun_inf                                               as infection_municipality_id,

        -- outcome (0 = "não informado" no SINAN; a Base dos Dados também o trata como nulo)
        nullif(evolucao, '0')                                    as case_outcome,
        {{ parse_date_any('dt_obito') }}                         as death_date,
        {{ parse_date_any('dt_encerra') }}                       as case_closure_date,

        -- audit
        tp_sistema                                               as source_system_type,
        {{ parse_date_any('dt_digita') }}                        as data_entry_date
    from traduzido
)

select
    to_hex(md5(
        {{ concat_ws('|', [
            'notification_date',
            'notification_municipality_id',
            'disease_code',
            'patient_birth_year',
            'patient_sex',
            'symptom_onset_date'
        ]) }}
    ))                                                           as case_id,
    *
from final

{% endif %}
