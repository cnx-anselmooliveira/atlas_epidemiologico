# Spec Delta

## Purpose

Transformar os dados raw do BigQuery nas camadas bronze, silver e gold que alimentam a API e o modelo de AI, com execução reprodutível manualmente ou por orquestrador.

## ADDED Requirements

### Requirement: Camadas no BigQuery
A modelagem SHALL materializar as camadas `bronze`, `silver` e `gold` como datasets do BigQuery no mesmo projeto da camada raw, preservando os nomes das tabelas gold consumidas pela API.

#### Scenario: Build completo
- **WHEN** a modelagem é executada por completo
- **THEN** existem no BigQuery os datasets `bronze`, `silver` e `gold`
- **AND** cada tabela gold servida pela API existe com o mesmo nome usado hoje (ex.: `gold_dengue_epi_curve_weekly`)

### Requirement: Marca de geração nas tabelas gold
Toda tabela gold SHALL ter a coluna `gold_generated_at` com o mesmo valor em todas as linhas de uma execução.

#### Scenario: Consulta da última geração
- **WHEN** uma tabela gold é reconstruída
- **THEN** `MAX(gold_generated_at)` da tabela é o instante dessa execução
- **AND** todas as linhas têm o mesmo valor de `gold_generated_at`

### Requirement: Configuração por ambiente
A modelagem SHALL ler projeto GCP, localização e credenciais de variáveis de ambiente, de forma que o mesmo projeto rode na máquina local, em container e no Airflow sem editar arquivos.

#### Scenario: Execução em container
- **WHEN** a modelagem roda em container com as variáveis de projeto e credencial definidas
- **THEN** conecta ao BigQuery sem depender de `~/.dbt/profiles.yml` do usuário

### Requirement: Testes de dados bloqueiam a publicação
A execução da modelagem SHALL rodar os testes de dados declarados e terminar com código de saída diferente de zero quando algum teste com severidade de erro falhar.

#### Scenario: Teste falhando
- **WHEN** um teste `not_null` de uma coluna chave de um model falha
- **THEN** a execução termina com erro
- **AND** os models que dependem dele não são reconstruídos nessa execução

### Requirement: Seleção parcial
A modelagem SHALL permitir executar somente um subconjunto de models (por camada ou por model e seus dependentes).

#### Scenario: Reconstrução a partir de uma fonte
- **WHEN** a modelagem é executada selecionando os models que dependem da fonte da Colômbia
- **THEN** somente esses models e seus dependentes são reconstruídos
