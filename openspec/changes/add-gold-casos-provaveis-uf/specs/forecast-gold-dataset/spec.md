# Spec Delta

## Purpose

Fornecer aos modelos de previsão uma série semanal confiável de casos prováveis de dengue por UF, alinhada à definição oficial de vigilância e pronta para receber covariáveis.

## ADDED Requirements

### Requirement: Classificação final padronizada
O projeto SHALL padronizar a classificação final do SINAN, removendo espaços e mapeando cada código para uma categoria:
- `confirmado_dengue`: 1, 10;
- `confirmado_complicado`: 2;
- `confirmado_grave`: 3, 4, 12;
- `sinais_alarme`: 11;
- `descartado`: 5;
- `inconclusivo`: 8;
- `em_investigacao`: nulo ou 0;
- `outro`: códigos não listados.

Toda notificação SHALL receber exatamente uma categoria.

#### Scenario: Código com espaço
- **WHEN** uma notificação tem a classificação `"5 "`
- **THEN** ela é classificada como `descartado`

#### Scenario: Código desconhecido
- **WHEN** aparece um código fora da lista
- **THEN** a notificação é classificada como `outro` e o teste de distribuição avisa quando `outro` passa de 0,1% do total

### Requirement: Casos prováveis
A tabela SHALL ter a coluna `probable_cases`, igual ao número de notificações que não são `descartado`. O total de casos prováveis na tabela SHALL ser igual ao total de notificações não descartadas da silver que tenham UF e semana atribuíveis.

#### Scenario: Conferência de totais
- **WHEN** a tabela é construída
- **THEN** a soma de `probable_cases` bate com a contagem de notificações não descartadas atribuíveis da silver, e um teste do dbt falha se não bater

### Requirement: Semana do início dos sintomas
A semana de cada caso SHALL ser a semana epidemiológica (domingo a sábado) da data de início dos sintomas. Quando essa data estiver ausente, for posterior à notificação ou anterior a ela em mais de 60 dias, SHALL ser usada a data de notificação, e o caso SHALL ser contado em `date_fallback_cases`.

#### Scenario: Início dos sintomas incoerente
- **WHEN** um caso tem início dos sintomas 90 dias antes da notificação
- **THEN** ele entra na semana da notificação e é contado em `date_fallback_cases`

### Requirement: UF de residência
O caso SHALL ser atribuído à UF de residência do paciente. Quando ela estiver ausente, SHALL ser usada a UF de notificação, e o caso SHALL ser contado em `place_fallback_cases`.

#### Scenario: Residência diferente da notificação
- **WHEN** um paciente residente em GO é notificado no DF
- **THEN** o caso entra na série de GO

### Requirement: Série regular por UF
A tabela SHALL ter exatamente uma linha por UF (27) e semana, da primeira à última semana do período. Semanas sem notificação SHALL aparecer com zero casos.

#### Scenario: Unicidade e cobertura
- **WHEN** os testes do dbt rodam
- **THEN** não há duplicidade de (UF, semana), há 27 UFs, e cada UF tem todas as semanas entre o início e o fim do período

### Requirement: Indicadores de gravidade e desfecho
A tabela SHALL trazer por UF e semana: notificações totais, descartados, confirmados, casos com sinais de alarme, casos graves e óbitos, para uso como alvos ou features adicionais. SHALL valer `probable_cases ≤ notified_cases`.

#### Scenario: Consistência
- **WHEN** os testes rodam
- **THEN** nenhuma linha tem `probable_cases` maior que `notified_cases` ou contagem negativa

### Requirement: População anual e incidência
A tabela SHALL trazer a população da UF no ano da semana, a partir de uma série anual (censos e estimativas do IBGE). A origem de cada valor SHALL ficar indicada: `censo`, `estimativa`, `interpolado` (entre anos conhecidos) ou `extrapolado` (repete o último valor conhecido nos anos posteriores). A coluna `incidence` SHALL ser `probable_cases / population × 100.000`.

#### Scenario: Ano sem estimativa
- **WHEN** não há estimativa do IBGE para um ano entre dois anos conhecidos
- **THEN** a população é interpolada linearmente entre os anos vizinhos e marcada como `interpolado`

#### Scenario: Ano após a última estimativa
- **WHEN** a série tem semanas de um ano posterior ao último valor do IBGE
- **THEN** a população repete o último valor conhecido e é marcada como `extrapolado`

### Requirement: Relevo como covariável estática
A tabela SHALL trazer a elevação média e a declividade média da UF, agregadas a partir dos municípios do Copernicus DEM por cruzamento espacial com os municípios do IBGE, ponderadas pela área.

#### Scenario: Cobertura do relevo
- **WHEN** a tabela é construída
- **THEN** as 27 UFs têm `mean_elevation_m` e `mean_slope_deg` preenchidos, e o teste registra o percentual de municípios casados no cruzamento

### Requirement: Sem complemento de outras fontes
A tabela SHALL conter apenas dados do SINAN, sem complementar semanas recentes com fontes agregadas nacionais (como a OPAS), que não têm UF.

#### Scenario: Últimas semanas
- **WHEN** as últimas semanas do SINAN estão incompletas
- **THEN** a tabela traz os valores do SINAN como estão, e o descarte de semanas imaturas fica a cargo dos modelos
