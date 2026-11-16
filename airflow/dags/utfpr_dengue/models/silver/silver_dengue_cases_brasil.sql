-- Silver: fato de casos de dengue do Brasil, nível de caso (grão = 1 caso
-- notificado). Único fato em grão de caso do modelo — mantido separado do
-- `silver_dengue_weekly_cases` porque é a única fonte com detalhe clínico/
-- demográfico rico o suficiente para justificar granularidade de caso.
--
-- NOTA: os valores possíveis de `case_classification` e `severe_dengue_flag`
-- seguem a codificação interna do SINAN (não documentada nas colunas
-- disponíveis) — não foi feita nenhuma tentativa de mapear esses códigos
-- para rótulos de negócio (ex. "confirmado"/"descartado") aqui, para não
-- inventar uma regra sem confirmar o dicionário de dados do SINAN.

select
    c.case_id,

    -- CORRIGIDO (2ª vez — a 1ª correção estava errada, ver histórico):
    -- verificado contra o dado real (dbt show) que notification_epi_week
    -- É majoritariamente "AAAA-SS" (ex. "2024-15"), mas existe uma minoria
    -- de linhas só com a semana ("SS", sem traço) e uma minoria com o campo
    -- em branco. notification_year (coluna `ano` do SINAN) é 100% não-nulo
    -- e sempre confiável — usar direto, nunca o que vem do split. Pra
    -- semana: pega a parte depois do traço quando existir (offset 1); se
    -- não tiver traço, o offset 1 fica nulo e cai pro offset 0 (a semana
    -- "solta"). Um CASE de sanidade descarta semana fora de 1-53 (valor
    -- corrompido).
    --
    -- FALLBACK (2026-09-23, investigando um "buraco" de 2020 inteiro no
    -- gráfico de cobertura): confirmado direto no SINAN raw
    -- (br_ms_sinan.duckdb) que `semana_notificacao` vem 100% em branco
    -- pros ~1,49M casos de 2020 — não é um bug do nosso parsing, é a
    -- própria fonte que não populou esse campo naquele ano (todo o resto
    -- do dado de 2020, incluindo `notification_date`, está completo).
    -- Como `notification_date` nunca falta, cai pra
    -- EXTRACT(ISOWEEK FROM notification_date) quando o campo de origem
    -- não dá pra parsear — calibrado contra os anos onde o campo original
    -- É confiável (2019/2021/2022): bate exatamente com o valor de origem
    -- em 93,5% das linhas (o resto é a divergência normal de convenção de
    -- semana epidemiológica vs. ISO nas viradas de ano).
    c.notification_year                                          as notification_epi_year,
    case
        when safe_cast(
                coalesce(
                    split(c.notification_epi_week, '-')[safe_offset(1)],
                    split(c.notification_epi_week, '-')[safe_offset(0)]
                ) as int64
             ) between 1 and 53
        then safe_cast(
                coalesce(
                    split(c.notification_epi_week, '-')[safe_offset(1)],
                    split(c.notification_epi_week, '-')[safe_offset(0)]
                ) as int64
             )
        when c.notification_date is not null
        then extract(isoweek from c.notification_date)
    end                                                           as notification_epi_week_number,
    c.notification_date,
    c.notification_state,
    c.notification_municipality_id,
    m_notif.municipality_name                                   as notification_municipality_name,

    c.symptom_onset_date,

    c.patient_state_residence,
    c.patient_municipality_residence_id,
    m_res.municipality_name                                     as patient_residence_municipality_name,
    c.patient_age,
    case
        when c.patient_age is null then null
        when c.patient_age < 1  then '<1'
        when c.patient_age < 5  then '1-4'
        when c.patient_age < 10 then '5-9'
        when c.patient_age < 15 then '10-14'
        when c.patient_age < 20 then '15-19'
        when c.patient_age < 50 then '20-49'
        when c.patient_age < 65 then '50-64'
        else '65+'
    end                                                          as patient_age_band,
    c.patient_sex,
    c.patient_race,
    c.patient_pregnancy_status,

    c.hospitalized_flag,
    c.hospitalization_date,

    c.case_classification,
    c.confirmation_criteria,
    c.severe_dengue_flag,
    c.autochthonous_case_flag,
    c.dengue_serotype,

    c.case_outcome,
    c.death_date,
    (c.death_date is not null)                                  as is_death,
    c.case_closure_date,
    date_diff(c.case_closure_date, c.notification_date, day)    as case_duration_days

from {{ ref('bronze_dengue_brasil') }} c
left join {{ ref('silver_dim_municipio_brasil') }} m_notif
    on c.notification_municipality_id = m_notif.municipality_id
left join {{ ref('silver_dim_municipio_brasil') }} m_res
    on c.patient_municipality_residence_id = m_res.municipality_id
