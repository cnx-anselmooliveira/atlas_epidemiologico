-- Aviso: códigos de classificação fora do dicionário acima de 0,1% das notificações.
{{ config(severity='warn') }}
select sum(other_cases) as outros, sum(notified_cases) as notificados
from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
having sum(other_cases) > 0.001 * sum(notified_cases)
