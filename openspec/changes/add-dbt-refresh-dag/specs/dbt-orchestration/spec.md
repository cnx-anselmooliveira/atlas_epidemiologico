# Spec Delta

## Purpose

Atualizar a modelagem dbt (bronze, silver e gold no BigQuery) pelo Airflow, sob demanda, com o mesmo código e as mesmas regras em dev, hml e prod.

## ADDED Requirements

<!-- Disparo, ordem por camada, regras de falha e escrita fora da pasta de DAGs foram
     redefinidos pela mudança add-cosmos-dbt-dags (execução pelo Cosmos, uma tarefa por
     model). Aqui ficam só os requisitos que valem para qualquer forma de execução. -->

### Requirement: Mesmo projeto e credencial por ambiente
A DAG SHALL usar o projeto dbt que está junto das DAGs (`airflow/dags/utfpr_dengue/`). O profile SHALL vir do próprio projeto e ler projeto, dataset, localização e chave de variáveis de ambiente, sem depender de arquivos pessoais.

#### Scenario: Airflow de hml
- **WHEN** a DAG roda no Airflow de hml, que lê as DAGs da branch `hml`
- **THEN** o dbt executado é o da branch `hml`, com a credencial configurada na stack de hml

### Requirement: Pasta de DAGs sem ruído
O projeto dbt dentro da pasta de DAGs SHALL ser ignorado pelo processador de DAGs. Os diretórios gerados pelo dbt SHALL NOT entrar na imagem do Airflow nem no git.

#### Scenario: Processamento das DAGs
- **WHEN** o processador de DAGs varre a pasta
- **THEN** ele não lê arquivos de `utfpr_dengue/`, e a lista de DAGs não tem erros de importação
