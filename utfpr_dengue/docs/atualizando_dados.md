# Atualizando os dados (runbook)

Passo a passo pra quando algo muda na fonte (novo ano carregado, schema
diferente, província/departamento novo aparecendo) e precisa propagar
Bronze → Silver → Gold → parquet local → front.

## 1. Rodando dbt depois de mudar um model/seed

```
cd utfpr_dengue
uv run dbt seed --select <nome_do_seed>       # só se mexeu num seed/*.csv
uv run dbt run --select <model>+              # o model mudado + tudo que depende dele
```

`profiles.yml` (`~/.dbt/profiles.yml`, perfil `utfpr_dengue`) precisa
apontar pra um `keyfile` válido do BigQuery — não commitado, cada
desenvolvedor tem o seu.

## 2. Re-exportando Gold → parquet local (pro front/API pegarem o dado novo)

A API já faz isso sozinha (embutido no `lifespan`, no startup + de hora em
hora — ver `infra/api/app/gold_sync.py`), mas pra forçar na hora sem
esperar:

```
cd infra/api
uv run scripts/sync_gold.py
```

Compara `gold_generated_at` (coluna em toda tabela Gold) entre BigQuery e
o parquet local; só reexporta o que estiver desatualizado.

## 3. Arquivos brutos sobrepostos da Argentina (`microdados/argentina_microdados_datos.salud/`)

**Investigado em 2026-09-23**, a partir de uma suspeita levantada sobre
`sum(case_count)` de 2024 dar 1.745.259 (bem acima do real). O portal de
dados abertos do Ministerio de Salud publica recortes SOBREPOSTOS do
mesmo período em arquivos diferentes (snapshot parcial vs. cumulativo do
ano inteiro, mesma exportação em 2 formatos, arquivo "atualización"
substituindo o original) — o loader antigo (`scripts/carregar_bigquery.py::carregar_argentina`)
concatenava todo arquivo da pasta sem checar sobreposição.

Confirmado linha a linha (`GROUP BY arquivo_origem, ano`) antes de excluir
qualquer arquivo — não foi só o 2024 que o usuário notou, o problema era
sistêmico:

| Ano | Duplicação encontrada | Arquivo mantido |
|---|---|---|
| 2018 | mesmo período em `.csv` (922 linhas) e `.xls` (660 linhas) | `.csv` (mais linhas recuperadas) |
| 2021 | `julio 2021.xlsx` (parcial, 3.850 casos) + `Diciembre 2021.xlsx` (ano inteiro, 3.991 casos — já contém o de julho) | `Diciembre 2021.xlsx` |
| 2024 | `2024.csv` + `2024_actualización_casos.csv` + `2024-2025.csv` (apesar do nome, só tem dado de 2024) — 3 cópias quase idênticas de ~581-582 mil casos cada | `2024_actualización_casos.csv` (nome indica ser a versão corrigida) |
| 2025 | `1 al 53 - 2025.csv` (17.695 casos) redundante com a parte de 2025 do rolante `(Se 1 2025 - Se 35 2026).csv` (17.696 casos, cobre 2025 **e** 2026) | `(Se 1 2025 - Se 35 2026).csv` |

Os 5 arquivos supersedidos ficam listados (com o porquê de cada um) em
`ARGENTINA_ARQUIVOS_SUPERSEDIDOS` em `scripts/carregar_bigquery.py`, e o
loader agora pula eles automaticamente. **2024 caiu de 1.745.259 para
581.433** (bronze) / 554.224 (silver, depois do filtro `%dengue%` e do
join com a província — ver seção 4 abaixo).

Se um arquivo novo aparecer nessa pasta no futuro: antes de rodar o
loader, checar se o período dele já está coberto por outro arquivo
existente (mesma query de `GROUP BY arquivo_origem, ano_calc` usada nessa
investigação) — não assumir que arquivo novo = período novo.

```sql
-- detecta sobreposição: mais de 1 arquivo com dado no mesmo ano
select
  coalesce(safe_cast(anio_min as int64), safe_cast(`año` as int64), safe_cast(ano as int64)) as ano_calc,
  arquivo_origem,
  count(*) n_rows,
  sum(safe_cast(coalesce(cantidad, cantidad_casos) as int64)) total_casos
from `ppgcc-dengue-project.microdados.raw_uftpr_microdados_argentina`
group by 1, 2
order by 1, 2
```

Pra recarregar depois de mexer na lista de exclusão:

1. `cd scripts && uv run carregar_bigquery.py argentina`
2. `cd ../utfpr_dengue && uv run dbt run --select bronze_dengue_argentina+`
3. Rodar o passo 2 deste runbook (re-exportar parquet).

## 4. Dicionário de província da Argentina (`seed_dim_provincia_argentina`)

O campo `admin1_name` da Argentina na Gold é nível **província** (não
departamento — departamento sozinho não é uma chave única no Brasil todo,
só dentro de cada província, ver comentário em
`models/silver/silver_dengue_weekly_cases.sql`). A resolução
departamento→província usa o `province_code`/`province_name` que **já
vem na fonte bruta** (INDEC), só normalizado (zero à esquerda, colunas às
vezes trocadas) e casado contra `seeds/seed_dim_provincia_argentina.csv`
(24 códigos INDEC → nome oficial, com acentuação corrigida — a fonte
bruta vem com mojibake tipo "C�rdoba").

Se aparecer um `province_code` novo que a fonte não tinha antes (ex.
reorganização administrativa), o `inner join` do model dropa essas linhas
silenciosamente (mesmo comportamento hoje pro código placeholder `99`/
`desconocida`, ~4-5% dos casos brutos). Pra corrigir:

1. Adicionar a linha no CSV: `utfpr_dengue/seeds/seed_dim_provincia_argentina.csv`.
2. `uv run dbt seed --select seed_dim_provincia_argentina --full-refresh`
3. `uv run dbt run --select silver_dengue_weekly_cases+`
4. Rodar o passo 2 deste runbook (re-exportar parquet).

Query pra achar `province_code`s não mapeados (deveria vir vazia se o
seed está completo):

```sql
select distinct a.province_code, a.province_name
from `ppgcc-dengue-project.bronze.bronze_dengue_argentina` a
left join `ppgcc-dengue-project.bronze.seed_dim_provincia_argentina` dim
  on lpad(regexp_extract(coalesce(a.province_code, a.province_name), r'^(\d{1,2})$'), 2, '0') = dim.province_code
where dim.province_code is null
```

## 5. Shape de estado/depto (front/public/geo/estados/*.json)

Regenerar depois de qualquer mudança nos nomes de `admin1_name` da Gold
(ex. depois do passo 3 acima) ou pra adicionar um país novo:

```
cd scripts
uv run gerar_geojson_estados_america_sul.py       # COL, PER, ECU, BOL, ARG
uv run gerar_geojson_america_sul.py               # base América do Sul (nível país)
```

O script já valida contra o dado real (query direta no parquet/BigQuery,
ver `scripts/gerar_geojson_estados_america_sul.py`) e avisa se algum nome
do shape não bate com nenhum `admin1_name` real, ou vice-versa — não
adivinha correspondência, só casa por dobra ASCII + um dicionário
`ALIAS` explícito pros casos que precisam (sigla, nome abreviado etc.).

**Limitação conhecida**: o geoBoundaries não publica shape ADM1 pra
**Entre Ríos** (Argentina) — falta inteira do dataset upstream (23 de 24
províncias). Não inventamos a geometria; a região fica sem área clicável
no mapa (mas os KPIs/curva epidemiológica continuam corretos, incluindo
esses casos). Ver `shapesFaltando` em `front/src/lib/paises.ts`.

## 6. População (incidência por 1.000 hab. no mapa)

Duas tabelas Gold-dimensão, wrappers finos sobre seeds estáticas (não
recalculam nada, só adicionam `gold_generated_at` pra entrar no mesmo
mecanismo de sync):

- `gold_dim_populacao_admin1` (seed `seed_populacao_admin1.csv`) — estado/
  província dos 6 países. Fontes documentadas no topo de
  `scripts/gerar_seed_populacao_admin1.py` (censo oficial por país, anos-base
  diferentes).
- `gold_dim_populacao_municipio_brasil` (seed `seed_populacao_municipio_brasil.csv`)
  — IBGE Censo 2022, todos os 5.570 municípios (API SIDRA, gerado por
  `scripts/gerar_seed_populacao_admin1.py` + fetch direto, ver o script).
- `gold_dim_populacao_departamento_argentina` (seed
  `seed_populacao_departamento_argentina.csv`) — INDEC Censo 2022, gerado
  por `scripts/gerar_seed_populacao_departamento_argentina.py` a partir de
  `arg_censo.xlsx` (planilhas Cuadro 1.1-1.24, uma por província) — 491 de
  ~520 deptos da Gold têm população (o resto são deptos reais sem nenhum
  caso histórico, ou combinações província×depto inconsistentes na fonte
  bruta — ver comentário no model Gold).

Pra atualizar (novo censo, país novo etc.): editar o CSV ou reexecutar o
script gerador, `dbt seed --select <seed> --full-refresh`, `dbt run
--select <gold_dim_...>`, depois passo 2 deste runbook.

## 7. Departamento da Argentina (drill-down de nível 3, como o município do Brasil)

`gold_dengue_departamento_epi_curve_weekly_argentina` — mesma ideia do
`gold_dengue_municipio_epi_curve_weekly`, mas a chave real é
`department_name` (dobra ASCII), não `department_code`: a fonte bruta usa
formatos diferentes do mesmo código entre arquivos de anos distintos
(“Comuna 1” da CABA aparece como “001”, “02001” e “2001”), então
`department_code` na Gold é só informativo (lineage), nunca uma chave de
join confiável — ver comentário no model.

Shape geográfico: `front/public/geo/departamentos/<province_code>.json`,
gerado por `scripts/gerar_geojson_departamentos_argentina.py` via spatial
join (centróide do depto dentro do polígono da província, mesma técnica
do município brasileiro) + correção manual documentada no script pra um
artefato de imprecisão de fronteira entre CABA e a Grande Buenos Aires.

**Limitação conhecida**: o geoBoundaries só publica 4 das 15 comunas reais
de CABA no nível ADM2 (gap upstream, não inventamos as faltantes) — o
resto dos dados de CABA continua correto via KPIs/curva, só não aparece
como área clicável no mapa de depto.

Pra regenerar depois de qualquer mudança: rodar o passo 1 pro model, o
passo 2 (parquet), depois `uv run gerar_geojson_departamentos_argentina.py`
de dentro de `scripts/`.

## 8. Front

Depois de qualquer passo acima que gere novo parquet ou geojson, só dar
refresh no browser (dev server já serve os arquivos direto de
`front/public/`) — não precisa rebuild. Variáveis de ambiente do front
(`VITE_API_BASE_URL`, `VITE_DEFAULT_PAIS`) ficam em `front/.env` (ver
`front/README.md`).
