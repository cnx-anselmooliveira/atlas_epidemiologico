# Spec Delta

## Purpose

Permitir que qualquer pessoa (ou o CI, ou o Airflow) execute o projeto dbt de forma reprodutível, sem depender de arquivos pessoais nem de credenciais versionadas.

## ADDED Requirements

### Requirement: Profile por variáveis de ambiente
O projeto dbt SHALL ter um `profiles.yml` versionado que lê o projeto GCP, a localização e a credencial de variáveis de ambiente, com o caminho da chave vindo de uma variável e nunca do conteúdo versionado. Executar o dbt SHALL NOT exigir o `~/.dbt/profiles.yml` do usuário.

#### Scenario: Máquina nova
- **WHEN** alguém clona o repositório, define as variáveis do profile e roda `dbt debug --profiles-dir airflow/dags/utfpr_dengue`
- **THEN** a conexão com o BigQuery é validada sem nenhum arquivo em `~/.dbt/`

### Requirement: Dependências fixadas
A versão do dbt e do adaptador BigQuery SHALL ficar fixada num lockfile do projeto, executável com um único comando (`uv run dbt …`).

#### Scenario: Mesma versão em todo lugar
- **WHEN** o dbt é executado no notebook e no CI
- **THEN** as duas execuções usam a mesma versão do `dbt-core` e do `dbt-bigquery`

### Requirement: Sem credenciais nem artefatos no repositório
O repositório SHALL NOT conter chaves, `target/`, `logs/` nem `dbt_packages/` do projeto dbt.

#### Scenario: Conferência antes do commit
- **WHEN** o projeto dbt é adicionado ao repositório
- **THEN** a varredura de segredos não encontra chaves, e os diretórios gerados estão ignorados pelo git

### Requirement: Validação sem acesso ao BigQuery
O projeto SHALL poder ser compilado e validado estruturalmente (`dbt parse`) sem credenciais, e essa validação SHALL rodar no pipeline de testes.

#### Scenario: Erro de referência num model
- **WHEN** um model referencia um `ref()` inexistente
- **THEN** o job `dbt` do CI falha apontando o model
