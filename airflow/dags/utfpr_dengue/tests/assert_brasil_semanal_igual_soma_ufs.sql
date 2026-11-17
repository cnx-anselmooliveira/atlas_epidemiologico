-- A gold nacional é a soma exata das UFs: mesmas semanas e mesmos totais de casos prováveis
-- e de população. Retorna as semanas que divergem (deve voltar vazio).
with ufs as (
    select week_start, sum(probable_cases) as probable_cases, sum(population) as population
    from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
    group by week_start
)

select
    coalesce(b.week_start, u.week_start) as week_start,
    b.probable_cases as brasil_probable,
    u.probable_cases as ufs_probable,
    b.population as brasil_population,
    u.population as ufs_population
from {{ ref('gold_dengue_casos_provaveis_brasil_semanal') }} as b
full outer join ufs as u on u.week_start = b.week_start
where b.week_start is null
    or u.week_start is null
    or b.probable_cases != u.probable_cases
    or b.population != u.population
