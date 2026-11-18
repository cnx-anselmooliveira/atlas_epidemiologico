# Spec Delta

## Purpose

Servir ao site, com cache, o que a exportação materializou no BigQuery, no mesmo padrão de segurança e de custo das rotas gold.

## ADDED Requirements

### Requirement: Rotas de previsão
A API SHALL expor, somente com GET, as rotas `/forecast/models`, `/forecast/metrics-uf`, `/forecast/predictions`, `/forecast/figures/{model}` e `/forecast/figures/{model}/{arquivo}`. Só as linhas vigentes SHALL ser servidas.

#### Scenario: Conteúdo das rotas
- **WHEN** o cliente consulta cada rota
- **THEN** `/forecast/models` traz família, versão, `data_version`, `trained_at` e as métricas de teste de cada modelo e horizonte
- **AND** `/forecast/metrics-uf` traz as métricas por UF, filtráveis por `model`, `horizon` e `split`
- **AND** `/forecast/figures/{model}` lista nome, legenda e horizonte das figuras, sem o caminho do bucket
- **AND** `/forecast/figures/{model}/{arquivo}?horizon=` devolve o PNG do horizonte (padrão 1)

#### Scenario: Previsão de um modelo
- **WHEN** o cliente chama `/forecast/predictions?model=catboost&horizon=2&uf=SP&split=future`
- **THEN** a resposta traz só as linhas futuras do CatBoost, horizonte 2, de São Paulo

### Requirement: Filtros parametrizados e paginação
Os valores de filtro SHALL ir ao banco como parâmetros de consulta e só colunas da whitelist SHALL ser filtráveis. As rotas de dados SHALL aceitar `limit` (padrão 200, máximo 1000) e `offset` e rejeitar valor acima do máximo com HTTP 422.

#### Scenario: Valor malicioso
- **WHEN** o cliente envia um `model` com texto de injeção de SQL
- **THEN** a resposta é uma lista vazia e nenhum SQL foi alterado

### Requirement: Cache por geração das tabelas
As respostas SHALL passar pelo cache Redis, com a chave incluindo a geração da tabela. Em até 5 minutos depois de uma nova exportação, as respostas SHALL refletir os dados novos. Sem Redis, a API SHALL continuar respondendo direto do BigQuery.

#### Scenario: Nova exportação
- **WHEN** a exportação reescreve `forecast_predictions`
- **THEN** em até 5 minutos `/forecast/predictions` devolve os dados novos, sem invalidação manual

### Requirement: Figuras seguras e em cache
A rota de figuras SHALL servir só arquivos PNG registrados em `forecast_figures` para o modelo pedido, rejeitar qualquer caminho fora dessa lista com HTTP 404, responder com `Cache-Control` de longa duração e `Content-Type: image/png` e nunca expor o caminho do bucket.

#### Scenario: Caminho forjado
- **WHEN** o cliente pede uma figura com `..` no nome do arquivo
- **THEN** a resposta é 404

### Requirement: Disponibilidade
Sem nenhuma exportação feita, as rotas de dados SHALL devolver lista vazia com HTTP 200, e falha do BigQuery SHALL ser HTTP 503, como nas demais rotas.

#### Scenario: Antes da primeira exportação
- **WHEN** o dataset `forecast` ainda não tem linhas vigentes
- **THEN** `/forecast/models` responde 200 com lista vazia
