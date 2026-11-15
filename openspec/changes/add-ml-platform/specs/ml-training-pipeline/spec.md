# Spec Delta

## Purpose

Fornecer um projeto de treino único que roda igual no notebook, em container e disparado pelo Airflow, servindo de base para o futuro modelo de nicho ecológico.

## ADDED Requirements

### Requirement: Mesmo comando em todo lugar
O treino SHALL ser iniciado por um único comando de linha de comando (ex.: `atlas-ml train <experimento>`), idêntico na máquina local, no container de treino e na tarefa do Airflow.

#### Scenario: Container de treino
- **WHEN** a imagem de treino é executada com `atlas-ml train example`
- **THEN** o resultado no MLflow tem a mesma estrutura de run que a execução local do mesmo comando

### Requirement: Configuração por ambiente
O destino do MLflow, o ambiente (`dev`, `hml`, `prod`), o projeto GCP e as credenciais SHALL vir de variáveis de ambiente validadas na inicialização. Um valor de ambiente fora de `dev`, `hml` e `prod` SHALL interromper a execução.

#### Scenario: Variável obrigatória ausente
- **WHEN** o treino é iniciado sem a URL do MLflow
- **THEN** a execução termina com erro listando a variável ausente, antes de qualquer processamento

### Requirement: Contrato de registro da run
Cada treino SHALL registrar:
- os hiperparâmetros;
- ao menos uma métrica de avaliação num conjunto separado do treino;
- o modelo serializado com assinatura de entrada e saída;
- um artefato com o resumo dos dados usados.

#### Scenario: Experimento de exemplo
- **WHEN** `atlas-ml train example` termina
- **THEN** a run tem parâmetros, a métrica de validação, o modelo com assinatura e o arquivo de resumo dos dados

### Requirement: Experimento de exemplo sem dependência externa
O experimento de exemplo SHALL usar dados sintéticos gerados com semente fixa, sem acessar o BigQuery, para validar o fluxo da plataforma de ponta a ponta.

#### Scenario: Mesma semente
- **WHEN** o experimento de exemplo roda duas vezes com a mesma semente
- **THEN** as duas runs registram a mesma métrica de validação

### Requirement: Leitura de features do BigQuery
O projeto SHALL oferecer uma interface de leitura de features do BigQuery que recebe a consulta ou tabela e devolve um dataframe com o resumo de linhas, colunas e período. A versão dos dados registrada SHALL incluir a geração da tabela (`gold_generated_at` ou a última modificação).

#### Scenario: Leitura de uma tabela gold
- **WHEN** a interface lê uma tabela do dataset `gold`
- **THEN** devolve os dados e um identificador de versão que inclui a data de geração da tabela

### Requirement: Testes automatizados
O projeto SHALL ter testes que rodam sem rede (MLflow em diretório temporário e BigQuery simulado) e que cobrem configuração, contrato de registro e experimento de exemplo.

#### Scenario: CI sem credenciais
- **WHEN** os testes rodam no CI sem nenhuma credencial
- **THEN** todos passam
