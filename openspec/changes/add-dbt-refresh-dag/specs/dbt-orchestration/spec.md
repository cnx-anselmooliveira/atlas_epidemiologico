# Spec Delta

## Purpose

Atualizar a modelagem dbt (bronze, silver e gold no BigQuery) pelo Airflow, sob demanda, com o mesmo código e as mesmas regras em dev, hml e prod.

## ADDED Requirements

### Requirement: Disparo manual com seleção
A DAG `process_etl_atlas` SHALL ter `schedule=None`, no máximo uma execução ativa e os parâmetros:
- `select`: padrão vazio, que significa o projeto inteiro;
- `exclude`;
- `full_refresh`: padrão falso.

Os parâmetros SHALL ser repassados ao dbt.

#### Scenario: Build parcial
- **WHEN** a DAG é disparada com `select=+gold_dengue_casos_provaveis_uf_semanal`
- **THEN** cada camada reconstrói e testa só os antecedentes dessa tabela que estão nela, na ordem seed, bronze, silver e gold

#### Scenario: Disparo durante outra execução
- **WHEN** a DAG é disparada enquanto outra execução dela está em andamento
- **THEN** a nova execução espera a anterior terminar

### Requirement: Ordem e regras de falha
A DAG SHALL executar, em sequência, uma tarefa por etapa:
1. a verificação de conexão (`dbt debug`);
2. `deps`;
3. `seed` (seeds e seus testes);
4. bronze, silver e gold, cada camada um `dbt build` (models e testes) restrito à sua pasta;
5. o relatório da execução.

Uma falha em qualquer etapa SHALL impedir as etapas seguintes. Uma falha de model ou teste SHALL falhar a tarefa da camada. O relatório SHALL rodar mesmo quando uma etapa falha, e a execução da DAG SHALL terminar com falha nesse caso.

#### Scenario: Credencial inválida
- **WHEN** a chave da service account é inválida
- **THEN** a tarefa de verificação falha com a mensagem do dbt e nenhuma camada é executada

#### Scenario: Teste de dados falhando na silver
- **WHEN** um teste do dbt falha na camada silver
- **THEN** a tarefa da silver falha e a gold não é executada
- **AND** o relatório lista o teste que falhou e a etapa
- **AND** a execução da DAG fica com falha

### Requirement: Relatório da execução
Ao final, a DAG SHALL resumir no log e no retorno da tarefa (XCom):
- quantos nós passaram, falharam, foram pulados ou tiveram aviso;
- os nomes dos que falharam;
- os mais demorados.

#### Scenario: Execução bem-sucedida
- **WHEN** o build termina sem erros
- **THEN** o relatório mostra zero falhas e os 5 nós mais lentos com seus tempos

### Requirement: Mesmo projeto e credencial por ambiente
A DAG SHALL usar o projeto dbt que está junto das DAGs (`airflow/dags/utfpr_dengue/`). O profile SHALL vir do próprio projeto e ler projeto, dataset, localização e chave de variáveis de ambiente, sem depender de arquivos pessoais.

#### Scenario: Airflow de hml
- **WHEN** a DAG roda no Airflow de hml, que lê as DAGs da branch `hml`
- **THEN** o dbt executado é o da branch `hml`, com a credencial configurada na stack de hml

### Requirement: Artefatos fora da pasta de DAGs
Os artefatos do dbt (`target/`, logs e `run_results.json`) SHALL ser gravados num diretório gravável separado por execução da DAG, nunca dentro da pasta de DAGs.

#### Scenario: Pasta de DAGs somente leitura
- **WHEN** a pasta de DAGs é montada como somente leitura
- **THEN** a DAG executa normalmente e os artefatos ficam no diretório da execução

### Requirement: Pasta de DAGs sem ruído
O projeto dbt dentro da pasta de DAGs SHALL ser ignorado pelo processador de DAGs. Os diretórios gerados pelo dbt SHALL NOT entrar na imagem do Airflow nem no git.

#### Scenario: Processamento das DAGs
- **WHEN** o processador de DAGs varre a pasta
- **THEN** ele não lê arquivos de `utfpr_dengue/`, e a lista de DAGs não tem erros de importação
