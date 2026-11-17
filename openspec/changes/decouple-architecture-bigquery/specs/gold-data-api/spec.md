# Spec Delta

## Purpose

Servir as tabelas gold do BigQuery ao frontend por uma API HTTP somente leitura, rápida e de custo controlado graças a um cache de leitura.

## ADDED Requirements

### Requirement: Contrato das rotas gold preservado
A API SHALL expor as mesmas rotas `GET /gold/*`, parâmetros de filtro e campos JSON que a API atual do `projeto_epidemiologia`, para que o frontend funcione sem mudar os tipos de resposta.

#### Scenario: Curva epidêmica por país
- **WHEN** o cliente chama a rota de curva epidêmica semanal filtrando por `country_iso3=BRA`
- **THEN** a resposta é uma lista JSON com os mesmos campos de hoje (`country_iso3`, `year`, `epi_week`, `total_cases`, ...) só com linhas do Brasil

### Requirement: Rotas dos casos prováveis do Brasil
Além das rotas herdadas, a API SHALL expor:
- `GET /gold/casos-provaveis-brasil-semanal`, a partir de `gold_dengue_casos_provaveis_brasil_semanal`, filtrável por `epi_year`;
- `GET /gold/casos-provaveis-uf-semanal`, a partir de `gold_dengue_casos_provaveis_uf_semanal`, filtrável por `uf` e `epi_year`.

As linhas SHALL vir ordenadas por semana (e por `uf` na rota por UF).

#### Scenario: Campos da resposta
- **WHEN** o cliente chama qualquer uma das duas rotas
- **THEN** cada linha traz pelo menos `week_start`, `epi_year`, `epi_week`, `probable_cases`, `population`, `incidence` e `gold_generated_at`
- **AND** a rota por UF traz também `uf`

#### Scenario: Série de uma UF
- **WHEN** o cliente chama `/gold/casos-provaveis-uf-semanal?uf=SP&limit=1000`
- **THEN** a resposta traz só linhas de SP, da semana mais antiga para a mais recente

#### Scenario: Ano para o mapa
- **WHEN** o cliente chama `/gold/casos-provaveis-uf-semanal?epi_year=2024&limit=1000`
- **THEN** a resposta traz as semanas de 2024 das 27 UFs

### Requirement: Leitura direta do BigQuery
A API SHALL obter os dados das tabelas do dataset `gold` no BigQuery, sem depender de cópia local (parquet ou banco embutido) como fonte.

#### Scenario: Dado novo na gold
- **WHEN** uma tabela gold é reconstruída e o cache dessa tabela é invalidado
- **THEN** a próxima requisição à rota correspondente retorna os dados da nova geração

### Requirement: Filtros parametrizados
Valores de filtro recebidos na requisição SHALL ser enviados ao banco como parâmetros de consulta, nunca concatenados ao SQL, e somente colunas permitidas por rota SHALL ser filtráveis.

#### Scenario: Filtro com texto malicioso
- **WHEN** o cliente envia `admin1_name=' OR 1=1 --`
- **THEN** a API retorna apenas linhas cujo `admin1_name` é literalmente esse texto (lista vazia)

### Requirement: Paginação limitada
Toda rota gold SHALL aceitar `limit` e `offset`, com `limit` padrão 200 e máximo 1000, rejeitando valores acima do máximo com HTTP 422.

#### Scenario: Limite acima do máximo
- **WHEN** o cliente chama uma rota gold com `limit=5000`
- **THEN** a API responde HTTP 422

### Requirement: Cache de leitura
A API SHALL guardar no cache as respostas por combinação de rota, filtros e paginação, e responder do cache enquanto a entrada for válida, sem consultar o BigQuery.

#### Scenario: Requisição repetida
- **WHEN** a mesma requisição é feita duas vezes dentro da validade do cache
- **THEN** a segunda resposta é idêntica à primeira e não gera consulta ao BigQuery

### Requirement: Invalidação do cache por geração da gold
As entradas de cache de uma tabela SHALL deixar de ser usadas, em até 5 minutos, quando a tabela gold for reconstruída, e também ao expirar um TTL máximo configurável.

#### Scenario: Nova execução do dbt
- **WHEN** uma tabela gold é reconstruída pelo dbt
- **THEN** em até 5 minutos as requisições a essa tabela passam a refletir a nova geração
- **AND** entradas de outras tabelas continuam válidas

#### Scenario: Invalidação explícita
- **WHEN** um chamador autenticado com o token de administração aciona a invalidação de cache
- **THEN** todas as entradas de cache são descartadas
- **AND** a mesma chamada sem token válido é rejeitada com HTTP 401

### Requirement: Degradação sem cache
Se o cache estiver indisponível, a API SHALL continuar respondendo consultando o BigQuery diretamente.

#### Scenario: Redis fora do ar
- **WHEN** o serviço de cache não responde
- **THEN** as rotas gold continuam retornando HTTP 200 com dados do BigQuery

### Requirement: Health check
A API SHALL expor `GET /health` informando o estado da conexão com o BigQuery e com o cache, respondendo HTTP 200 quando o BigQuery está acessível.

#### Scenario: Dependências saudáveis
- **WHEN** BigQuery e cache estão acessíveis
- **THEN** `GET /health` responde HTTP 200 com ambos marcados como disponíveis

#### Scenario: BigQuery inacessível
- **WHEN** a credencial do BigQuery é inválida
- **THEN** `GET /health` responde HTTP 503

### Requirement: CORS restrito
A API SHALL aceitar requisições de navegador somente das origens configuradas e somente com o método GET nas rotas públicas.

#### Scenario: Origem não autorizada
- **WHEN** um navegador em uma origem fora da lista configurada chama a API
- **THEN** a resposta não inclui cabeçalho `Access-Control-Allow-Origin` para essa origem
