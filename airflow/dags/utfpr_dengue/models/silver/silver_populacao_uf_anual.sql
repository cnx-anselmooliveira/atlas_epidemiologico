-- População residente por UF e ano (2000 até o ano corrente), do seed gerado a partir
-- do SIDRA/IBGE (scripts/gerar_seed_populacao_uf_anual.py). Interpolação e
-- extrapolação já resolvidas no seed; a coluna origin diz de onde veio cada valor.

{{ config(materialized='view') }}

select
    uf,
    year,
    population,
    origin,
    source
from {{ ref('seed_populacao_uf_anual') }}
