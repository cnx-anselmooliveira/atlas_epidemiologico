-- 27 UFs, e cada uma com todas as semanas entre a primeira e a última do período.
with gold as (
    select uf, week_start from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
),
esperado as (
    select date_diff(max(week_start), min(week_start), week) + 1 as semanas,
           count(distinct uf) as ufs
    from gold
),
por_uf as (
    select uf, count(*) as semanas from gold group by uf
)
select p.uf, p.semanas, e.semanas as esperado, e.ufs
from por_uf as p cross join esperado as e
where p.semanas != e.semanas or e.ufs != 27
