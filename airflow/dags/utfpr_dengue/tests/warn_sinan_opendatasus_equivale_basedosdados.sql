-- Aviso: equivalência entre as duas fontes do SINAN, nos anos presentes em ambas.
--   Anos fechados (até 2020): total de notificações por UF idêntico, exceto 2014 e 2015.
--   2014 e 2015 são exceções conhecidas e aceitas: o arquivo do OpenDataSUS não traz os
--   descartados nem os confirmados do esquema antigo (casos prováveis 8,4% e 4,5% abaixo da
--   Base dos Dados; ver docs/referencias/sinan-opendatasus.md).
--   Anos republicados (2021+): total por UF do OpenDataSUS >= 90% do da Base dos Dados. O
--   OpenDataSUS continua atualizando esses anos depois do retrato da Base dos Dados, então
--   ganha notificações novas e reclassifica casos (por isso a classificação final não entra).
--   Ano corrente: fora do teste. As notificações ainda mudam de classe entre as publicações
--   ("sem classificação" e "inconclusivo" viram confirmado/descartado), então ele só é
--   documentado.
-- Linhas retornadas = divergências. A UF do OpenDataSUS vem como código do IBGE (2007+) ou
-- sigla (2000-2006); o ano é o do arquivo, como o `ano` da Base dos Dados. Nulos viram
-- '(vazio)' para casar no full join (NULL = NULL não casa).
{{ config(severity='warn') }}

{%- set relacao = source('sinan_opendatasus', 'sinan_dengue_opendatasus') -%}
{%- if execute -%}
    {%- set existentes = adapter.get_columns_in_relation(relacao) | map(attribute='name') | list -%}
{%- else -%}
    {%- set existentes = [] -%}
{%- endif %}

with ufs as (
    select distinct div(municipality_id, 100000) as codigo, state_code as sigla
    from {{ ref('bronze_dim_municipio_brasil') }}
    where municipality_id is not null
),

opendatasus as (
    select
        s.ano_arquivo as ano,
        coalesce(u.sigla, {{ sinan_col('SG_UF_NOT', existentes) }}, '(vazio)') as uf,
        coalesce({{ sinan_coalesce_col(['CLASSI_FIN', 'CON_CLASSI'], existentes) }}, '(vazio)') as classificacao,
        count(*) as n
    from {{ relacao }} as s
    left join ufs as u
        on regexp_contains(s.SG_UF_NOT, r'^\d{2}$') and u.codigo = safe_cast(s.SG_UF_NOT as int64)
    group by 1, 2, 3
),

basedosdados as (
    select
        safe_cast(ano as int64) as ano,
        coalesce(sigla_uf_notificacao, '(vazio)') as uf,
        coalesce(nullif(trim(cast(classificacao_final as string)), ''), '(vazio)') as classificacao,
        count(*) as n
    from {{ source('raw_uftpr_microdados', 'raw_uftpr_microdados_brasil') }}
    group by 1, 2, 3
),

anos_comuns as (
    select ano from (
        select distinct ano from opendatasus
        intersect distinct
        select distinct ano from basedosdados
    )
    where ano < extract(year from current_date())
),

por_uf as (
    select ano, uf, sum(o.n) as n_opendatasus, sum(b.n) as n_basedosdados
    from (select ano, uf, sum(n) as n from opendatasus group by 1, 2) as o
    full join (select ano, uf, sum(n) as n from basedosdados group by 1, 2) as b using (ano, uf)
    group by 1, 2
)

select 'ano fechado: total por UF diferente' as regra, ano, uf, cast(null as string) as classificacao,
       n_opendatasus, n_basedosdados
from por_uf
where ano in (select ano from anos_comuns)
  and ano <= 2020
  and ano not in (2014, 2015)
  and coalesce(n_opendatasus, 0) != coalesce(n_basedosdados, 0)

union all

select 'ano republicado: total por UF abaixo de 90%' as regra, ano, uf, cast(null as string) as classificacao,
       n_opendatasus, n_basedosdados
from por_uf
where ano in (select ano from anos_comuns)
  and ano >= 2021
  and coalesce(n_opendatasus, 0) < 0.90 * coalesce(n_basedosdados, 0)
