# Spec Delta

## Purpose

Disponibilizar o Airflow como serviço da plataforma, local e na VPS, para disparar treinos de ML agora e as DAGs de ingestão e dbt depois, com hml e prod isolados.

## ADDED Requirements

### Requirement: DAGs vindas do repositório
As DAGs SHALL ser versionadas em `airflow/dags/` no repositório público. Na VPS, o Airflow de hml SHALL lê-las diretamente da branch `hml` e o de prod da branch `main`, sem rebuild de imagem. Em dev, SHALL montá-las do diretório local. Nenhuma DAG SHALL ser editada diretamente no servidor.

#### Scenario: Nova DAG em hml
- **WHEN** uma DAG nova chega à branch `hml` por merge de `dev`
- **THEN** a DAG aparece no Airflow de hml sem nova imagem e não aparece no Airflow de prod

#### Scenario: Edição em dev
- **WHEN** um arquivo de DAG é alterado no diretório local
- **THEN** o Airflow de dev passa a refletir a alteração sem rebuild de imagem

### Requirement: Metadados persistentes e isolados
Cada instalação do Airflow (dev, hml, prod) SHALL usar um banco de metadados próprio e persistente. Histórico de execuções de hml SHALL NOT aparecer em prod.

#### Scenario: Recriar a stack de prod
- **WHEN** a stack do Airflow de prod é recriada
- **THEN** o histórico de execuções e as conexões configuradas continuam disponíveis

### Requirement: Integração com o MLflow
O Airflow SHALL receber por configuração a URL e as credenciais do MLflow, e o ambiente (`hml`, `prod`) que suas tarefas usam como `atlas.env`.

#### Scenario: Treino disparado em hml
- **WHEN** a DAG de exemplo roda no Airflow de hml
- **THEN** a run aparece no MLflow da VPS com `atlas.env=hml` e `atlas.image_tag=hml`

### Requirement: DAG de exemplo de treino
A plataforma SHALL incluir uma DAG, sem agendamento automático, que executa `atlas-ml train example` e falha se a run não for registrada no MLflow.

#### Scenario: MLflow indisponível
- **WHEN** a DAG de exemplo roda com o MLflow fora do ar
- **THEN** a tarefa falha após as retentativas configuradas e a falha fica visível na interface com o log

### Requirement: Acesso autenticado e sem exposição interna
A interface do Airflow na VPS SHALL exigir login e ser servida apenas por HTTPS. Componentes internos (scheduler, banco, processador de DAGs) SHALL NOT ter portas expostas à internet. Em dev, a interface SHALL escutar apenas em `127.0.0.1`.

#### Scenario: Acesso anônimo na VPS
- **WHEN** alguém abre a URL do Airflow de prod sem estar autenticado
- **THEN** é redirecionado para a tela de login

### Requirement: Health check e recuperação
Os componentes do Airflow SHALL ter health check e reinício automático em caso de falha.

#### Scenario: Scheduler cai
- **WHEN** o processo do scheduler termina com erro
- **THEN** o orquestrador de containers o reinicia e as DAGs voltam a ser agendadas
