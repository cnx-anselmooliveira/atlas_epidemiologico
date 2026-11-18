-- AVULSO (fora da ETL): amostra pequena da gold de casos prováveis para testar o pipeline de
-- previsão de ponta a ponta em minutos. Só existe quando se liga a variável adhoc_amostra:
--
--   ./airflow/dags/utfpr_dengue/dbt.sh run --select gold_dengue_casos_provaveis_uf_semanal_amostra --       --vars '{adhoc_amostra: true}'
--   (opcional) --vars '{adhoc_amostra: true, amostra_ufs: [SP, MG], amostra_ano_inicial: 2018}'
--
-- Mesmas colunas da gold, só algumas UFs e os anos mais recentes. Fica no schema `adhoc`, nunca
-- no `gold`, e as DAGs da ETL (Cosmos) não enxergam o modelo porque ele vem desligado.

{{ config(
    materialized='table',
    schema='adhoc',
    enabled=var('adhoc_amostra', false),
    cluster_by=['uf'],
) }}

select *
from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
where uf in ({% for u in var('amostra_ufs', ['SP', 'MG', 'RJ', 'PR']) %}'{{ u }}'{{ ',' if not loop.last }}{% endfor %})
    and epi_year >= {{ var('amostra_ano_inicial', 2016) }}
