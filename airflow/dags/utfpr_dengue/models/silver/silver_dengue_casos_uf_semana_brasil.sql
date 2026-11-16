-- Silver agregada: notificações de dengue do SINAN por UF de residência e semana
-- epidemiológica do início dos sintomas. Lê a silver de casos (33 mi de linhas) uma
-- única vez; a gold de casos prováveis lê só este agregado.
--
-- Regras (spec forecast-gold-dataset):
--   data: início dos sintomas; cai para a notificação quando ausente, posterior à
--         notificação ou mais de 60 dias antes dela (contado em date_fallback_cases);
--   lugar: UF de residência; cai para a UF de notificação (place_fallback_cases);
--   classificação: macro sinan_classificacao; prováveis = tudo menos 'descartado'.
-- Notificações sem data e sem UF atribuíveis ficam fora (conferido pelo teste de totais).

{{ config(materialized='table', cluster_by=['uf']) }}

with casos as (
    select
        notification_date,
        symptom_onset_date,
        patient_state_residence,
        notification_state,
        is_death,
        {{ sinan_classificacao('case_classification') }} as classificacao,
        (
            symptom_onset_date is null
            or symptom_onset_date > notification_date
            or date_diff(notification_date, symptom_onset_date, day) > 60
        ) as fallback_data
    from {{ ref('silver_dengue_cases_brasil') }}
),

atribuidos as (
    select
        coalesce(patient_state_residence, notification_state) as uf,
        {{ epi_week_start('if(fallback_data, notification_date, symptom_onset_date)') }} as week_start,
        classificacao,
        fallback_data,
        patient_state_residence is null as fallback_lugar,
        is_death
    from casos
    where notification_date is not null
      and coalesce(patient_state_residence, notification_state) is not null
)

select
    uf,
    week_start,
    count(*) as notified_cases,
    countif(classificacao != 'descartado') as probable_cases,
    countif(classificacao = 'descartado') as discarded_cases,
    countif(classificacao like 'confirmado_%' or classificacao = 'sinais_alarme') as confirmed_cases,
    countif(classificacao in ('sinais_alarme', 'confirmado_complicado')) as alarm_cases,
    countif(classificacao = 'confirmado_grave') as severe_cases,
    countif(classificacao = 'inconclusivo') as inconclusive_cases,
    countif(classificacao = 'em_investigacao') as investigation_cases,
    countif(classificacao = 'outro') as other_cases,
    countif(is_death and classificacao != 'descartado') as deaths,
    countif(fallback_data) as date_fallback_cases,
    countif(fallback_lugar) as place_fallback_cases
from atribuidos
group by uf, week_start
