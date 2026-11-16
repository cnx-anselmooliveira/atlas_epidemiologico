# Spec Delta

## Purpose

Rodar a modelagem dbt pelo Airflow com visibilidade por model: cada model e seus testes aparecem como tarefas próprias, na ordem das camadas.

## ADDED Requirements

### Requirement: Uma tarefa por model, por camada
A DAG `process_etl_atlas` SHALL representar cada seed e cada model do projeto dbt como tarefa própria, com os testes do model executados logo depois dele. As tarefas SHALL ser agrupadas por camada e os grupos SHALL rodar em sequência: seed, bronze, silver e gold. Todo model do projeto SHALL pertencer a exatamente um grupo.

#### Scenario: Grafo da DAG
- **WHEN** a DAG é aberta no Airflow
- **THEN** existem os grupos `seed`, `bronze`, `silver` e `gold`, nessa ordem, e o grupo `gold` contém a tarefa de `gold_dengue_casos_provaveis_uf_semanal`

#### Scenario: Model novo
- **WHEN** um model é adicionado a `models/silver/` e a DAG é relida
- **THEN** ele aparece como tarefa no grupo `silver`, sem mudança no código da DAG

### Requirement: Falha localizada
A falha de um model ou de um teste SHALL falhar a tarefa daquele model. Tarefas que dependem dela SHALL NOT rodar, e a execução da DAG SHALL terminar com falha. Não haverá retentativa automática.

#### Scenario: Teste falhando na silver
- **WHEN** um teste de um model da silver falha
- **THEN** a tarefa daquele model fica com falha, as tarefas que dependem dele na gold não rodam, e a execução fica vermelha
- **AND** o nome do model que falhou aparece na própria tarefa, sem precisar procurar no log

### Requirement: Disparo sem configuração
A DAG SHALL ter `schedule=None`, no máximo uma execução ativa e nenhum parâmetro obrigatório. O disparo SHALL rodar o projeto inteiro. Para refazer só parte da modelagem, SHALL bastar limpar (clear) as tarefas ou o grupo desejado.

#### Scenario: Refazer só a gold
- **WHEN** alguém limpa o grupo `gold` de uma execução já terminada
- **THEN** só as tarefas da gold rodam de novo

### Requirement: Projeto e credencial do ambiente, sem escrita na pasta de DAGs
A execução SHALL usar o projeto dbt que está junto das DAGs e o profile do próprio projeto, com credencial por variável de ambiente. A pasta de DAGs SHALL NOT receber arquivos gerados pela execução, já que pode ser somente leitura no bundle Git.

#### Scenario: Pasta de DAGs somente leitura
- **WHEN** a pasta de DAGs está montada como somente leitura
- **THEN** a DAG roda normalmente
