# Spec Delta

## Purpose

Fornecer aos modelos de previsão um painel de incidência de dengue por UF e semana, versionado e dividido no tempo sem vazamento, pronto para receber covariáveis ambientais no futuro.

## ADDED Requirements

### Requirement: Painel de incidência a partir da gold do SINAN
O dataset SHALL ser montado a partir da gold `gold_dengue_casos_provaveis_uf_semanal` do BigQuery: casos prováveis (`probable_cases`, notificações não descartadas) por UF de residência e semana do início dos sintomas, com a população da UF no ano epidemiológico. A incidência SHALL ser calculada como casos por 100 mil habitantes. Cada linha SHALL ser única por (UF, data de início da semana). As covariáveis estáticas da gold (`mean_elevation_m`, `mean_slope_deg`) SHALL acompanhar o painel.

#### Scenario: Montagem do painel
- **WHEN** o dataset é preparado
- **THEN** existe uma linha por UF e semana epidemiológica, com `cases`, `population`, `incidence`, os canais epidemiológicos e as covariáveis de relevo
- **AND** não há duas linhas com a mesma UF e semana

### Requirement: Canais epidemiológicos no painel
O painel SHALL carregar os canais epidemiológicos da gold: `notified_cases`, `discarded_cases`, `confirmed_cases`, `alarm_cases`, `severe_cases`, `inconclusive_cases`, `investigation_cases` e `deaths`. As colunas de qualidade (`other_cases`, `date_fallback_cases`, `place_fallback_cases`) e de proveniência (`population_year`, `population_origin`, `gold_generated_at`) SHALL NOT virar canais de entrada.

#### Scenario: Colunas de qualidade
- **WHEN** as janelas são montadas
- **THEN** nenhuma coluna de qualidade ou de proveniência aparece entre as features

#### Scenario: UF sem população
- **WHEN** uma UF da gold não tem população
- **THEN** a preparação falha listando a UF, em vez de gerar incidência nula ou infinita

### Requirement: Semanas faltantes explícitas
Semanas sem registro dentro do período de uma UF SHALL ser incluídas com zero casos e uma marca de preenchimento, de modo que as janelas temporais tenham espaçamento regular. A gold já entrega a série regular; o dataset valida e completa por segurança.

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
O dataset SHALL produzir janelas com N semanas de histórico (padrão 12) e alvo H semanas à frente (padrão 1), por UF, registradas como parâmetros da run. As features SHALL incluir o histórico de incidência, a sazonalidade (semana do ano), a identidade da UF. Covariáveis adicionais SHALL poder ser acrescentadas sem mudar a interface dos modelos.

#### Scenario: Janela multivariada
- **WHEN** as janelas são montadas com a configuração padrão de features
- **THEN** cada janela tem, por passo, a incidência e todos os canais epidemiológicos, e a entrada tabular tem `window × (1 + n_canais)` valores de histórico mais sazonalidade e UF

#### Scenario: Nova covariável no futuro
- **WHEN** uma coluna de covariável (ex.: temperatura) é adicionada ao painel e listada na configuração de features
- **THEN** ela entra nas janelas de entrada de todos os modelos sem alteração no código deles

### Requirement: Canais em cada passo da janela
Cada passo da janela SHALL levar os canais epidemiológicos do painel como taxas por 100 mil habitantes, como na referência, e a configuração padrão de features SHALL listá-los.

#### Scenario: Configuração padrão
- **WHEN** a configuração de features não é alterada
- **THEN** todos os canais epidemiológicos do painel entram em cada passo

### Requirement: Canais só com o passado
Nenhum canal da semana-alvo, nem de semana posterior à origem da janela, SHALL entrar nas features. As transformações dos canais (taxa por 100 mil, `log1p`, padronização) SHALL ser ajustadas apenas no treino, como as da incidência.

#### Scenario: Canal contemporâneo ao alvo
- **WHEN** uma janela tem origem na semana t e alvo na semana t+H
- **THEN** `confirmed_cases`, `deaths` e os demais canais entram somente até a semana t
- **AND** os valores de t+1 em diante não aparecem em nenhuma feature

### Requirement: Maturidade dos canais
O corte de semanas imaturas SHALL considerar o canal que consolida mais devagar (classificação final e óbitos), e não apenas os casos prováveis. O corte usado SHALL ser registrado como parâmetro da run.

#### Scenario: Canal ainda em consolidação
- **WHEN** as últimas semanas do painel têm `confirmed_cases` ou `deaths` sistematicamente abaixo do valor consolidado
- **THEN** o painel de treino as descarta antes da divisão e o `drop_recent_weeks` registrado reflete o corte adotado
