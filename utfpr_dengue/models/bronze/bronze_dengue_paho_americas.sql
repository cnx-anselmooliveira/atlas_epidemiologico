-- Bronze: dengue de todas as Américas (PAHO/ARBO Portal), fallback para
-- países sem fonte nacional. Grão = país/subregião × ano × semana
-- epidemiológica. "Total of Dengue Cases" é cumulativo dentro do ano civil
-- (des-acumulado na Silver).
--
-- Carregada com `column_name_character_map="V2"` (ver
-- scripts/carregar_bigquery.py::carregar_paho). Regra CONFIRMADA ao vivo
-- (3 exemplos reais): "." "(" ")" "/" viram "_" (um a um, sem colapsar
-- underscores nem remover espaços), mas "%" e letras acentuadas são
-- preservados como estão — ex.: "In / Out of Subregions" ->
-- "In _ Out of Subregions", "Epi. Week (a)" -> "Epi_ Week _a_",
-- "% Lab Conf (x100)" -> "% Lab Conf _x100_" (só o parêntese muda, o "%"
-- fica). Apliquei essa regra às demais colunas com parênteses/"/" abaixo
-- por analogia — se alguma ainda der "Unrecognized name", provavelmente é
-- porque tem outro caractere que essa regra não cobre.

select
    safe_cast(`ID` as string)                                       as source_record_id,
    `Country or Subregion`                                          as country_or_subregion,
    `Serotype`                                                      as dengue_serotype,
    safe_cast(`Year` as int64)                                      as notification_year,
    `In _ Out of Subregions`                                        as subregion_flag,
    safe_cast(`Epi_ Week _a_` as int64)                              as notification_epi_week,

    safe_cast(`Total of Dengue Cases _b_` as int64)                 as cumulative_total_cases,
    safe_cast(`Incidence Rate _c_` as float64)                      as incidence_rate,
    safe_cast(`Laboratory Confirmed` as int64)                      as laboratory_confirmed_cases,
    safe_cast(`% Lab Conf _x100_` as float64)                       as pct_lab_confirmed,
    safe_cast(`Severe Dengue _d_` as int64)                         as severe_dengue_cases,
    safe_cast(`_SD_D_ x100 _e_` as float64)                         as pct_severe_over_total,
    safe_cast(`Deaths` as int64)                                    as deaths,
    safe_cast(`CFR _f_` as float64)                                 as case_fatality_rate,
    safe_cast(replace(safe_cast(`Population X 1000` as string), ',', '') as float64)
                                                                     as population_thousands

from {{ source('raw_uftpr_microdados', 'raw_uftpr_paho_dengue') }}
