# utfpr_dengue (dbt)

Modelagem da dengue no BigQuery (`ppgcc-dengue-project`, location US), em camadas `bronze` (views sobre `microdados`), `silver` e `gold`. O projeto fica junto das DAGs porque o Airflow o executa pela DAG `process_etl_atlas`.

## Como rodar

**Pelo Airflow** (dev, hml, prod): dispare a DAG `process_etl_atlas`. Sem configuração, ela roda o projeto inteiro:

```
dbt_debug ► dbt_deps ► dbt_seed ► dbt_bronze ► dbt_silver ► dbt_gold ► dbt_report
```

Parâmetros opcionais:
- `select`: seletores do dbt, por exemplo `+gold_dengue_casos_provaveis_uf_semanal`. Cada camada roda só o que estiver nela.
- `exclude`: seletores a excluir.
- `full_refresh`: recria as tabelas incrementais do zero.

Os artefatos (`target/`, logs, `run_results.json`) ficam em `/opt/airflow/dbt-artifacts/<run_id>/<etapa>/`, nunca nesta pasta.

**Localmente:**
```bash
./airflow/dags/utfpr_dengue/dbt.sh debug
./airflow/dags/utfpr_dengue/dbt.sh build --select +gold_dengue_casos_provaveis_uf_semanal
```
No PowerShell, use `dbt.ps1` com os mesmos argumentos. Os scripts:
- usam o `uv` com as versões travadas no `uv.lock` (dbt-core 1.12.7, dbt-bigquery 1.12.3);
- usam o `profiles.yml` desta pasta, só com variáveis de ambiente;
- usam a chave `platform/secrets/training-sa.json`, que não é versionada;
- gravam os artefatos em `.dbt-local/`, ignorado pelo git.

| Variável | Padrão | Uso |
|---|---|---|
| `DBT_BQ_KEYFILE` | obrigatória (scripts: `platform/secrets/training-sa.json`; containers: `/secrets/training-sa.json`) | chave da service account |
| `DBT_GCP_PROJECT` | `ppgcc-dengue-project` | projeto GCP |
| `DBT_BQ_DATASET` | `ppgcc-dengue-dataset` | dataset padrão; os schemas vêm da macro `generate_schema_name` |
| `DBT_BQ_LOCATION` | `US` | localização |
| `DBT_THREADS` | `4` | paralelismo |

A service account de treino tem escrita em `silver` e `gold`, conferida com `dbt run --select silver_dim_country`.

## Tabelas para os modelos de previsão

- **`gold_dengue_casos_provaveis_uf_semanal`:**
  - casos prováveis (notificações não descartadas) por UF de residência e semana epidemiológica do início dos sintomas;
  - 27 UFs × todas as semanas desde 2000, com zero onde não houve notificação;
  - população do ano epidemiológico, incidência por 100 mil habitantes e relevo da UF.
  - Comparação com a curva antiga em [`docs/referencias/gold-casos-provaveis-uf.md`](../../../docs/referencias/gold-casos-provaveis-uf.md).
- **`silver_dengue_casos_uf_semana_brasil`:** o agregado por UF e semana. Lê os 33 milhões de notificações uma vez por build.
- **`silver_relevo_uf_brasil`:** relevo do Copernicus DEM ADM2 por UF, com cruzamento espacial com os centroides do IBGE.
- **`silver_populacao_uf_anual`** e o seed **`seed_populacao_uf_anual`:** população por UF e ano, do SIDRA/IBGE. Para atualizar: `python airflow/dags/utfpr_dengue/scripts/gerar_seed_populacao_uf_anual.py`.
- **Macros:**
  - `sinan_classificacao`: classificação final do SINAN;
  - `epi_week_start`, `epi_year` e `epi_week`: semana epidemiológica de domingo a sábado.

## Testes

`dbt build` roda os testes de cada camada logo depois dos seus models. Os testes singulares ficam em `tests/`:
- os totais de casos prováveis batem entre a silver, o agregado e a gold;
- prováveis ≤ notificados;
- semanas completas por UF;
- relevo presente nas 27 UFs;
- aviso de códigos de classificação desconhecidos.

## Custo e tempo do build completo

Execução da `process_etl_atlas` sem parâmetros, em dev, em 16/11/2026:

| Etapa | Nós | Resultado |
|---|---|---|
| seed | 5 seeds, 16 testes | ok |
| bronze | 9 views | ok |
| silver | 7 tabelas/views, 15 testes | ok |
| gold | 16 tabelas, 15 testes | ok |
| **total** | **83 nós** | **0 erros, 0 avisos** |

- **Tempo:** 128 s somando as etapas do dbt; cerca de 4,7 min de DAG, contando a partida de cada tarefa.
- **Dados processados:** 9,19 GiB no BigQuery. A maior parte vem da `silver_dengue_cases_brasil` (3,2 GiB) e das golds que leem os 33 milhões de notificações.
- **Nó mais lento:** `gold_dengue_alert_level_weekly` (19,9 s).
