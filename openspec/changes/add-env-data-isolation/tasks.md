# Tasks

## 1. Ambiente em um só lugar

- [x] 1.1 Criar `airflow/dags/atlas_ingest/ambiente.py` (ambiente a partir de `ATLAS_ENV`, sufixo dos datasets, prefixo do landing, nomes completos da bronze e da gold, erro para ambiente desconhecido) e os testes sem rede para dev, hml, prod e inválido; verificar com os testes na imagem do Airflow
- [x] 1.2 Equivalente em `atlas_ml` para a gold lida pelo treino (`forecast/dataset.py` deixa de fixar `gold`), com teste; verificar com `pytest` do `ml/`

## 2. Ingestão e decisões

- [x] 2.1 `atlas_ingest/sinan.py` usa o prefixo e o dataset da bronze do ambiente (inclusive staging) e cria o dataset com `CREATE SCHEMA IF NOT EXISTS` (location `US`) antes do DDL da tabela; verificar com `test_sinan_ingest.py` e um teste novo do DDL do dataset
- [x] 2.2 `atlas_ingest/etl_brasil.py` e as DAGs usam as tabelas do ambiente nas decisões do dbt e do treino e registram no log o prefixo e os datasets; verificar com `test_etl_brasil.py` (dev, hml) e `test_dags.py`

## 3. dbt

- [x] 3.1 Macro `generate_schema_name` com o sufixo do ambiente e fonte `sinan_opendatasus` com o schema da bronze do ambiente; verificar com `dbt compile` (ou `dbt ls --output json`) com `ATLAS_ENV=dev` (schemas `bronze`/`silver`/`gold`) e `ATLAS_ENV=hml` (`*_hml`, fonte em `bronze_hml`)
- [x] 3.2 `dbt_brasil` dispara a `process_dbt_docs_atlas` ao fim do grupo `gold` (sem esperar); verificar com teste de DAG (tarefa depois do `gold`, pulada quando `decidir_dbt` pula)

## 4. Stack e configuração

- [x] 4.1 `docker-compose.yml`: `ATLAS_FORECAST_DATASET`, `BQ_DATASET_GOLD` e `BQ_DATASET_FORECAST` do ambiente (padrões `forecast_<ambiente>` e `gold_<ambiente>`), e `.env.example` comentado; verificar com `check-stack.sh` e `check-secrets --all`

## 5. Verificação e primeira carga

- [ ] 5.1 Rodar a suíte (testes do Airflow, `ml`, `ruff`, `check-stack`) e promover pelo fluxo de PR, com a aprovação do usuário
- [ ] 5.2 Na VPS, com a aprovação do usuário: despausar a `etl_brasil` e dispará-la com `forcar_treino`; verificar o landing em `landing/hml/sinan/dengue/`, os datasets `bronze_hml`, `silver_hml`, `gold_hml` e `forecast_hml` criados e preenchidos, a docs em `dbt_docs/hml/`, e o site de hml lendo a gold e as previsões de hml
- [ ] 5.3 Conferir que os dados de dev não mudaram (última modificação de `bronze`, `silver`, `gold`, `forecast` e do landing de dev antes e depois) e registrar tempos e custo da primeira carga em `docs/referencias/resultados-forecast-br.md`
