# Design

## Context

Observado:

- Bucket único no projeto: `ppgcc-bucket` (`SOUTHAMERICA-EAST1`), com os prefixos `br_ms_sinan/`, `cosmos_cache/`, `dbt_docs/`, `forecast/`, `landing/` e `mlflow/`. `mlflow/`, `cosmos_cache/` e `dbt_docs/` já são separados por ambiente; `landing/sinan/dengue/` não.
- `atlas_ingest/sinan.py`: `PREFIXO_LANDING = "landing/sinan/dengue/"` e `DATASET_BRONZE = "bronze"` fixos (a tabela é `bronze.sinan_dengue_opendatasus`, com staging `_stg_sinan_dengue_<ano>` no mesmo dataset). O estado do sync fica na metadata dos objetos do landing.
- dbt (`utfpr_dengue/`): `+schema: bronze|silver|gold` em `dbt_project.yml` (seeds em `bronze`); a macro `generate_schema_name` devolve exatamente o `custom_schema_name`; a fonte `sinan_opendatasus` aponta para `schema: bronze`; o profile tem location `US`.
- Treino: `ml/src/atlas_ml/forecast/dataset.py` fixa `GOLD = "ppgcc-dengue-project.gold"`; a DAG aceita `fonte`, mas a `etl_brasil` passa vazio.
- Exportação: `ATLAS_FORECAST_DATASET` (padrão `forecast`), figuras em `forecast/<ambiente>/...`. Backend: `bq_dataset_gold` e `bq_dataset_forecast` configuráveis por variável.
- `atlas_ingest/etl_brasil.py`: `BRONZE_SINAN` e `GOLD_CASOS` fixos nos datasets de dev.
- Na VPS de hml, `ATLAS_ENV=hml` já existe no stack; em dev, `ATLAS_ENV=dev` (`airflow/config/dev.env`).

## Goals / Non-Goals

**Goals:**
- hml e prod escrevem só nos seus dados; dev não muda.
- Uma só configuração (`ATLAS_ENV`) decide tudo, sem lista de variáveis para manter em sincronia.

**Non-Goals:**
- Migrar ou renomear os dados atuais de dev.
- Separar os datasets de origem só de leitura (`microdados` e afins).
- Projetos ou buckets separados por ambiente.
- Desligar o app legado do VPS ou mudar o que ele lê.

## Decisions

1. **Derivar do `ATLAS_ENV`, com sufixo vazio em dev.** `sufixo = "" se dev, "_<ambiente>" se hml ou prod`; ambiente desconhecido é erro. Em Python, num módulo único por pacote: `atlas_ingest/ambiente.py` (DAGs) e uma função em `atlas_ml` (treino), cada um com testes. No dbt, a macro `generate_schema_name` acrescenta o sufixo ao `custom_schema_name` e a fonte `sinan_opendatasus` monta o schema com a mesma regra em Jinja (`env_var('ATLAS_ENV', 'dev')`). Alternativa descartada: variáveis separadas por dataset (`ATLAS_BRONZE_DATASET`...), porque seriam quatro valores para manter coerentes em cada stack e um esquecimento misturaria ambientes.

2. **Landing: `landing/<ambiente>/sinan/dengue/` em hml e prod; dev mantém o caminho atual.** Mudar o de dev obrigaria a baixar tudo de novo ou a copiar a metadata de estado; o ganho seria só estético. Registrado como exceção de compatibilidade de dev.

3. **Prod com `_prod`, não com os nomes sem sufixo.** Os nomes sem sufixo já são do dev; usar os mesmos em prod repetiria o problema desta mudança.

4. **O que é configurável continua configurável, mas com padrão derivado.** `ATLAS_FORECAST_DATASET`, `BQ_DATASET_GOLD` e `BQ_DATASET_FORECAST` passam a ser definidos no stack a partir do ambiente (`forecast${sufixo}`...), e o `.env.example` explica. O backend não precisa de código novo.

5. **Criação dos datasets.** A ingestão executa `CREATE SCHEMA IF NOT EXISTS` da bronze do ambiente (location `US`) antes do DDL da tabela. O dbt-bigquery já cria os schemas dos models; a exportação já cria o dela. Nenhum passo manual.

6. **Docs do dbt disparada pela `dbt_brasil`, não pela `etl_brasil`.** Um `TriggerDagRunOperator` ao fim do grupo `gold` (sem esperar) só roda quando o dbt rodou, porque o `decidir_dbt` pula tudo o que vem depois; vale também quando a `dbt_brasil` é disparada à mão. Na `etl_brasil` seria preciso repetir a decisão "o dbt rodou?". Cumpre a decisão do usuário ("rodar após o dbt") com menos lógica.

7. **Primeira carga de hml pela própria `etl_brasil`.** Com o landing de hml vazio, a ingestão vê todos os anos como novos; o dbt roda porque a gold de hml não existe; o treino roda porque não há modelo vigente em hml. Basta despausar e disparar com `forcar_treino` (o treino roda de qualquer jeito, mas deixa explícito).

## Risks / Trade-offs

- **Custo e tempo da primeira carga:** baixar todos os arquivos anuais do OpenDataSUS (alguns GB), carregar a bronze e rodar o dbt completo (cerca de 9 GiB processados) e o treino da base inteira (horas na VPS). É uma vez só; os dias seguintes só processam o que mudou.
- **Armazenamento duplicado:** a bronze, a silver e a gold existem em dev e em hml (e depois em prod). Aceito em troca do isolamento.
- **Esquecer o `ATLAS_ENV`:** sem a variável, o padrão é `dev`; num container de hml isso escreveria nos dados de dev. Mitigação: o stack (`docker-compose.yml`) já exige `ATLAS_ENV` com `${ATLAS_ENV:?}`, e as DAGs registram no log o prefixo e os datasets usados.
- **Fonte do dbt em YAML:** o Jinja da fonte não enxerga macros próprias; a regra do sufixo fica escrita duas vezes no projeto dbt (macro e fonte). Um teste de compilação com `ATLAS_ENV=hml` confere as duas.
- **Cache do Cosmos:** os nomes dos datasets mudam o `dbt ls`; o cache já é por ambiente (`cosmos_cache/<ambiente>`), então não há mistura.
