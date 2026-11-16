# Design

## Context

O que foi observado no BigQuery e no projeto dbt `airflow/dags/utfpr_dengue/` (trazido do projeto antigo, ainda não versionado):

- **`silver_dengue_cases_brasil`:** tabela, 33,46 milhões de notificações, uma linha por caso. Tem `symptom_onset_date`, `notification_date`, `patient_state_residence`, `notification_state`, `case_classification` (texto cru do SINAN), `severe_dengue_flag`, `is_death` e `autochthonous_case_flag`.
- **`case_classification`:** a partir de 2013 os códigos vêm com espaço no fim (`"5 "`, `"8 "`, `"1 "`…), e antes sem espaço. Distribuição:
  - 10: 15,6 mi;
  - 1: 5,7 mi;
  - **5 (descartado): 7,21 mi**;
  - 8: 3,74 mi;
  - nulo: 0,64 mi;
  - 11: 0,26 mi;
  - 0: 0,15 mi;
  - 2/3/4/12: menores;
  - 6: 3 casos.
- **`silver_dengue_weekly_cases` → `gold_dengue_epi_curve_weekly`:** `count(*)` por `notification_state` e semana de notificação, sem filtrar classificação, mais o complemento nacional da OPAS (sem UF) nas semanas recentes.
- **Datas e lugar:** 298 mil casos têm início dos sintomas a mais de 60 dias da notificação; 5,2 mil não têm UF de residência; 131 mil têm UF de residência diferente da de notificação.
- **População:** `seed_populacao_admin1` só tem 2022 (Censo).
- **Relevo:** `microdados.raw_uftpr_geospatial_copernicus_dem_regions` tem para o Brasil **só ADM2** (5.556 municípios, com elevação mínima, máxima e média e declividade média, `geometry GEOGRAPHY`). O `region_id` é do geoBoundaries e não casa com o código do IBGE. `silver_dim_municipio_brasil` tem `centroid_wkt` e `state_code`.
- **Profile atual:** em `~/.dbt/profiles.yml` (pessoal), `method: service-account` com keyfile local, `location: US`, `dataset: ppgcc-dengue-dataset` e schemas customizados pela macro `generate_schema_name`.

## Goals / Non-Goals

**Goals:**
- Uma tabela gold pequena (cerca de 37 mil linhas: 27 UFs × cerca de 1.380 semanas) que os modelos leem inteira, com alvo correto e covariáveis estáticas.
- Lógica de classificação e de semana epidemiológica centralizada em macros reutilizáveis, para corrigir depois as tabelas do site com a mesma regra.
- O dbt rodando do repositório com um comando, sem arquivos pessoais.

**Non-Goals:**
- Alterar `silver_dengue_weekly_cases` ou as tabelas gold atuais. Fica como recomendação, numa mudança própria, porque afeta a API e o site.
- Nível de município.
- Incremental: a tabela é pequena; o custo está na leitura da silver, mitigado pela tabela intermediária agregada.

## Decisions

### 1. Projeto no repositório e execução
- **Pasta:** o projeto entra em `airflow/dags/utfpr_dengue/`, com o nome trazido. A `decouple-architecture-bigquery` previa `dbt/`, e o alinhamento fica registrado lá depois.
- **`airflow/dags/utfpr_dengue/pyproject.toml` + `uv.lock`:** dependências fixadas, `dbt-core` e `dbt-bigquery` (versões resolvidas e travadas no lock). A execução é `uv run --project utfpr_dengue dbt build --project-dir utfpr_dengue --profiles-dir airflow/dags/utfpr_dengue`, encapsulada em `airflow/dags/utfpr_dengue/dbt.ps1` e `dbt.sh`.
- **`airflow/dags/utfpr_dengue/profiles.yml` versionado:**
  ```yaml
  utfpr_dengue:
    target: dev
    outputs:
      dev:
        type: bigquery
        method: service-account
        project: "{{ env_var('DBT_GCP_PROJECT', 'ppgcc-dengue-project') }}"
        dataset: "{{ env_var('DBT_BQ_DATASET', 'ppgcc-dengue-dataset') }}"
        location: "{{ env_var('DBT_BQ_LOCATION', 'US') }}"
        keyfile: "{{ env_var('DBT_BQ_KEYFILE') }}"
        threads: 4
        job_retries: 1
        job_execution_timeout_seconds: 600
  ```
  Localmente, `DBT_BQ_KEYFILE` aponta para `platform/secrets/training-sa.json`; o script define o padrão. A service account precisa de permissão de escrita nos datasets `silver` e `gold`, o que é conferido na tarefa 1.
- **`.gitignore` do projeto:** já ignora `target/`, `logs/` e `dbt_packages/`. A varredura de segredos roda antes do primeiro commit.

### 2. Macros
- **`sinan_classificacao(col)`**: `CASE TRIM(col) WHEN '5' THEN 'descartado' …`, conforme o mapeamento da spec. Os códigos vêm do dicionário de dados do SINAN (CLASSI_FIN):
  - até 2013: 1 dengue clássica, 2 com complicações, 3 FHD, 4 SCD;
  - a partir de 2014: 10 dengue, 11 com sinais de alarme, 12 dengue grave;
  - 5 descartado; 8 inconclusivo.
  - O `0` (2000–2008 e alguns em 2024+) e o nulo são tratados como "em investigação". O `6`, com 3 casos, vira `outro`.
- **`epi_week_start(d)`**: `DATE_TRUNC(d, WEEK(SUNDAY))`, a semana epidemiológica brasileira de domingo a sábado.
- **`epi_year(week_start)`**: `EXTRACT(YEAR FROM DATE_ADD(week_start, INTERVAL 3 DAY))`, a regra da quarta-feira (a semana pertence ao ano com 4 ou mais dos seus dias). O número da semana é calculado a partir da primeira semana daquele ano.

### 3. Models
| Model | Materialização | Grão | Papel |
|---|---|---|---|
| `silver_dengue_casos_uf_semana_brasil` | table, cluster `uf` | UF × semana | Lê a silver de casos uma única vez e faz todas as contagens (notificados, descartados, prováveis, confirmados, sinais de alarme, graves, inconclusivos, em investigação, outros, óbitos entre prováveis, fallbacks de data e de lugar) |
| `silver_populacao_uf_anual` | view | UF × ano | Seed + interpolação/extrapolação já resolvidas no seed |
| `silver_relevo_uf_brasil` | table | UF | DEM ADM2 × `silver_dim_municipio_brasil` por `ST_CONTAINS(geometry, ST_GEOGPOINT(centroid))`; médias ponderadas por `ST_AREA(geometry)`; colunas de controle `municipios_dem`, `municipios_casados` e `taxa_casamento` |
| **`gold_dengue_casos_provaveis_uf_semanal`** | table, cluster `uf` | UF × semana | Calendário completo (27 UFs × todas as semanas entre a mínima e a máxima) LEFT JOIN contagens (nulos → 0) + população do ano epidemiológico + relevo + `incidence` + `gold_generated_at` |

Regra de data por caso, aplicada dentro do model silver agregado:
```sql
case when symptom_onset_date is null
       or symptom_onset_date > notification_date
       or date_diff(notification_date, symptom_onset_date, day) > 60
     then notification_date else symptom_onset_date end
```
A UF é `coalesce(patient_state_residence, notification_state)`. Casos sem nenhuma das duas (residuais) ficam fora e são contados no `data_summary` do teste de totais.

Colunas da gold:
- identificação: `uf`, `week_start`, `epi_year`, `epi_week`;
- contagens: `notified_cases`, `probable_cases`, `discarded_cases`, `confirmed_cases`, `alarm_cases`, `severe_cases`, `inconclusive_cases`, `investigation_cases`, `other_cases`, `deaths`, `date_fallback_cases`, `place_fallback_cases`;
- população e taxa: `population`, `population_year`, `population_origin`, `incidence`;
- relevo: `mean_elevation_m`, `mean_slope_deg`;
- `gold_generated_at`.

### 4. População anual por UF
`airflow/dags/utfpr_dengue/scripts/gerar_seed_populacao_uf_anual.py` consulta a API SIDRA do IBGE e grava `seeds/seed_populacao_uf_anual.csv` (`uf, year, population, origin, source`):
- **censos:** 2000, 2010 e 2022;
- **estimativas anuais:** tabela 6579, nos anos disponíveis;
- **anos sem valor entre dois conhecidos:** interpolação linear (`interpolado`);
- **anos após o último valor, até o ano corrente:** repetição do último (`extrapolado`).

O CSV versionado é a fonte da verdade do dbt. O script só é rodado para atualizar. Se o SIDRA estiver fora do ar, o script falha sem tocar no CSV.

### 5. Testes
- **Genéricos (`.yml`):**
  - `unique` na combinação `uf || week_start`;
  - `not_null` nas chaves e na população;
  - `accepted_values` de `population_origin`;
  - `accepted_values` das 27 siglas de UF.
- **Singulares (`tests/`):**
  - `assert_casos_provaveis_batem_com_silver.sql`: a soma de prováveis na gold é igual à contagem de não descartados atribuíveis na silver;
  - `assert_provaveis_menor_igual_notificados.sql`;
  - `assert_semanas_completas_por_uf.sql`;
  - `assert_relevo_27_ufs.sql`;
  - `warn_classificacao_outro.sql`, com `severity: warn`, para quando `outro` passar de 0,1%.

### 6. CI
O `ci.yml` ganha o job `dbt`:
- `uv sync --frozen` em `airflow/dags/utfpr_dengue/`;
- variáveis fictícias (`DBT_BQ_KEYFILE=/dev/null`);
- `dbt parse --profiles-dir .`;
- o job entra em `ci-ok`.

`dbt build` contra o BigQuery fica fora do CI, porque exigiria segredo; roda localmente e, depois, pelo Airflow.

### 7. Ajuste da `add-dengue-forecast-models`
- **Spec `forecast-dataset`:** o requisito "Painel de incidência a partir da gold do SINAN" passa a citar `gold_dengue_casos_provaveis_uf_semanal` e `probable_cases`. O preenchimento de semanas faltantes vira garantia da gold, e o dataset só valida.
- **Design (seção 2):** a consulta vira um `SELECT` simples da nova tabela. O painel ganha `mean_elevation_m` e `mean_slope_deg` como covariáveis estáticas disponíveis para `cfg.features`.
- **Código do módulo 2 (`forecast/dataset.py`, não commitado):** a constante `QUERY` e os testes do cliente simulado são ajustados quando aquele módulo for retomado.

## Ajustes da implementação

- **Pasta e execução:** o projeto ficou em `airflow/dags/utfpr_dengue/` (mudança `add-dbt-refresh-dag`), com `pyproject.toml`/`uv.lock`, `profiles.yml` por variáveis e os scripts `dbt.sh`/`dbt.ps1` (artefatos em `.dbt-local/`, ignorado). Em produção, roda pela DAG `process_etl_atlas`.
- **Início da série:** a gold começa no ano epidemiológico 2000 (`var('gold_first_epi_year', 2000)`), o primeiro com população no seed. Os poucos casos com início dos sintomas no fim de dezembro de 1999 ficam fora; o teste de totais confere silver → agregado e agregado (a partir de 2000) → gold.
- **Relevo:** cada polígono do DEM recebe a UF mais frequente entre os centroides do IBGE contidos nele; sem centroide contido, a do centroide mais próximo do centro do polígono. O teste exige ≥ 98% de casamento por contenção no país e ≥ 85% por UF (AP, RO e RR, com poucos polígonos, ficam entre 87% e 93%).
- **Fonte sem descartados desde 2022:** a classificação 5 some dos microdados a partir de 2022 (621 casos em 2022, zero depois). Os prováveis ficam consistentes em toda a série; a curva atual tem uma quebra de nível em 2022. Detalhes em `docs/referencias/gold-casos-provaveis-uf.md`.

## Risks / Trade-offs

- **[Custo de leitura: 33 milhões de linhas a cada build]** → o model silver agregado lê a silver uma vez, com colunas selecionadas; a gold lê só esse agregado. Pode virar incremental depois.
- **[Mapeamento de códigos do SINAN sem dicionário oficial no projeto]** → mapeamento documentado na macro com a fonte (dicionário CLASSI_FIN do SINAN) e teste de `outro` para códigos novos. A definição de "provável" (tudo menos descartado) não depende do detalhe dos códigos confirmados.
- **[Cruzamento espacial: centroide fora do polígono ou divergência geoBoundaries × IBGE]** → taxa de casamento registrada no model e conferida na tarefa. A média ponderada por área tolera alguns municípios faltantes.
- **[Permissão de escrita da SA local nos datasets]** → conferida antes do build (tarefa 1). Se faltar, o uso de outra chave fica documentado.
- **[SIDRA indisponível ou com tabela renumerada]** → o CSV versionado garante o build. O script falha com uma mensagem clara.

## Migration Plan

1. Versionar o projeto dbt e rodar `dbt build --select +gold_dengue_casos_provaveis_uf_semanal`.
2. Conferir os totais e o perfil da nova tabela contra a gold antiga, num relatório da tarefa: a diferença esperada é de cerca de 22%, os descartados.
3. Ajustar os artefatos da `add-dengue-forecast-models`.
4. **Rollback:** dropar a tabela nova. Nada existente depende dela.

## Open Questions

- Incluir só casos autóctones no alvo? Por padrão, não: a coluna fica disponível, mas o alvo é o de casos prováveis, como no indicador oficial.
