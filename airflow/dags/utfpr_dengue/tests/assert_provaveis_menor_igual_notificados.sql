-- Nenhuma linha com prováveis acima das notificações ou contagem negativa.
select *
from {{ ref('gold_dengue_casos_provaveis_uf_semanal') }}
where probable_cases > notified_cases
   or least(notified_cases, probable_cases, discarded_cases, confirmed_cases, deaths,
            date_fallback_cases, place_fallback_cases) < 0
   or probable_cases + discarded_cases != notified_cases
