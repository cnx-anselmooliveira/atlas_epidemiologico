# Spec Delta

## Purpose

Fornecer aos modelos de previsão um painel de incidência de dengue por UF e semana, versionado e dividido no tempo sem vazamento, pronto para receber covariáveis ambientais no futuro.

## ADDED Requirements

### Requirement: Painel de incidência a partir da gold do SINAN
O dataset SHALL ser montado a partir das tabelas gold do Brasil no BigQuery: casos semanais por UF da curva epidêmica e população por UF. A incidência SHALL ser calculada como casos por 100 mil habitantes, usando a população do ano mais próximo disponível. Cada linha SHALL ser única por (UF, data de início da semana).

#### Scenario: Montagem do painel
- **WHEN** o dataset é preparado
- **THEN** existe uma linha por UF e semana epidemiológica, com `cases`, `population` e `incidence`
- **AND** não há duas linhas com a mesma UF e semana

#### Scenario: UF sem população
- **WHEN** uma UF da curva epidêmica não tem população na tabela de população
- **THEN** a preparação falha listando a UF, em vez de gerar incidência nula ou infinita

### Requirement: Semanas faltantes explícitas
Semanas sem registro dentro do período de uma UF SHALL ser incluídas com zero casos e uma marca de preenchimento, de modo que as janelas temporais tenham espaçamento regular.

#### Scenario: Buraco na série
- **WHEN** a gold não tem linha para uma UF numa semana entre a primeira e a última semana dessa UF
- **THEN** o painel inclui essa semana com `cases=0` e `filled=true`

### Requirement: Snapshot versionado
Cada preparação SHALL gravar o painel como artefato (parquet) no MLflow e SHALL registrar a versão dos dados com as tabelas de origem e a data de geração de cada uma. Todos os modelos de uma mesma execução SHALL usar o mesmo snapshot.

#### Scenario: Execução da DAG
- **WHEN** os modelos-base de uma execução são treinados
- **THEN** todas as runs têm a mesma `atlas.data_version` e apontam para o mesmo artefato de dataset

### Requirement: Divisão temporal sem vazamento
O painel SHALL ser dividido no tempo em treino, validação e teste, com o teste formado pelas semanas mais recentes. Qualquer transformação ajustada aos dados (escalonamento, redução de dimensão, aumento de dados) SHALL ser ajustada apenas no treino e aplicada às demais partes. O teste SHALL NOT ser usado em ajuste, seleção de hiperparâmetros nem parada antecipada.

#### Scenario: Escalonamento
- **WHEN** o escalonador é ajustado
- **THEN** seus parâmetros dependem apenas das semanas de treino

#### Scenario: Limites das partes
- **WHEN** a divisão é feita com 52 semanas de teste e 52 de validação
- **THEN** o alvo de toda janela de teste está nas últimas 52 semanas e nenhuma janela de treino tem alvo nesse período

### Requirement: Janelas de entrada e alvo configuráveis
O dataset SHALL produzir janelas com N semanas de histórico (padrão 12) e alvo H semanas à frente (padrão 1), por UF, registradas como parâmetros da run. As features SHALL incluir o histórico de incidência, a sazonalidade (semana do ano) e a identidade da UF. Covariáveis adicionais SHALL poder ser acrescentadas sem mudar a interface dos modelos.

#### Scenario: Nova covariável no futuro
- **WHEN** uma coluna de covariável (ex.: temperatura) é adicionada ao painel e listada na configuração de features
- **THEN** ela entra nas janelas de entrada de todos os modelos sem alteração no código deles
