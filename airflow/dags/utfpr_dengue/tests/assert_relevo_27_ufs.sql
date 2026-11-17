-- Relevo para as 27 UFs. Casamento por contenção (centroide do IBGE dentro do polígono
-- do DEM) de pelo menos 98% no país e 85% em cada UF; o resto recebe a UF pelo
-- centroide mais próximo. UFs com poucos polígonos (AP, RR, RO) ficam perto de 90%.
with relevo as (
    select * from {{ ref('silver_relevo_uf_brasil') }}
)
select uf, taxa_casamento
from relevo
where taxa_casamento < 0.85
union all
select 'BR' as uf, round(sum(municipios_casados) / sum(municipios_dem), 4) as taxa_casamento
from relevo
having count(*) != 27 or sum(municipios_casados) / sum(municipios_dem) < 0.98
