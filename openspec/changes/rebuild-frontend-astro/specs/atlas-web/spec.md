# Spec Delta

## Purpose

Publicar o Atlas Epidemiológico da Dengue como site público, renderizado no servidor, que apresenta os indicadores das tabelas gold por país e por região, com visões que podem ser compartilhadas por link.

## ADDED Requirements

### Requirement: Renderização no servidor a partir do backend
Cada página SHALL ser renderizada no servidor com os dados obtidos das rotas `/gold/*` do backend, e o HTML entregue SHALL já conter os indicadores principais da página, sem depender de JavaScript no navegador.

#### Scenario: Página aberta sem JavaScript
- **WHEN** a página de um país é aberta com JavaScript desabilitado
- **THEN** o HTML exibe os KPIs do ano selecionado e a tabela de casos semanais desse país

### Requirement: Backend acessível apenas pelo servidor web
O navegador SHALL se comunicar somente com o domínio do site. A URL do backend SHALL ser lida de variável de ambiente do servidor em runtime e SHALL NOT aparecer no HTML ou no JavaScript enviados ao navegador.

#### Scenario: Troca da URL do backend
- **WHEN** o container do site é reiniciado com outro valor na variável de URL do backend
- **THEN** as páginas passam a usar o novo backend sem rebuild da imagem
- **AND** nenhum recurso enviado ao navegador contém essa URL

### Requirement: Página de panorama
A página inicial SHALL apresentar, para o ano selecionado, os KPIs por país da América do Sul (total de casos, incidência por 100 mil habitantes, variação em relação ao ano anterior), um mapa coroplético por país e a curva semanal de casos.

#### Scenario: Panorama do ano corrente
- **WHEN** a página inicial é aberta sem parâmetros
- **THEN** o ano selecionado é o ano mais recente com dados
- **AND** cada país com dados aparece nos KPIs e no mapa com link para a sua página

### Requirement: Página por país
Cada país com dados SHALL ter uma página com a curva epidêmica semanal (com média móvel de 3 semanas e comparação com a mesma semana do ano anterior), o nível de alerta das semanas recentes, a incidência semanal e o ranking das regiões (admin1).

#### Scenario: País existente
- **WHEN** a página do país `BRA` é aberta
- **THEN** são exibidos a curva semanal, o nível de alerta, a incidência e o ranking de estados do Brasil

#### Scenario: País inexistente
- **WHEN** a página de um código de país sem dados é aberta
- **THEN** o site responde HTTP 404 com uma página de "não encontrado" e um link para o panorama

### Requirement: Detalhe por região
Cada região (admin1) SHALL ter uma página com sua curva epidêmica semanal. Quando houver dado de nível inferior, a página SHALL também mostrar o mapa e o ranking dessas unidades: municípios para o Brasil e departamentos para a Argentina.

#### Scenario: Estado brasileiro
- **WHEN** a página de uma UF do Brasil é aberta
- **THEN** é exibida a curva semanal da UF, o mapa e o ranking dos seus municípios

#### Scenario: Região sem nível inferior
- **WHEN** a página de uma região de um país sem dado municipal é aberta
- **THEN** é exibida apenas a curva semanal da região, sem mapa de nível inferior e sem erro

### Requirement: Página de qualidade dos dados
O site SHALL ter uma página que mostra, por país e fonte, a cobertura temporal e os indicadores de qualidade da tabela gold de qualidade de dados, junto com a fonte oficial de cada país.

#### Scenario: Consulta da cobertura
- **WHEN** a página de qualidade dos dados é aberta
- **THEN** cada país aparece com a fonte de dados, o período coberto e os indicadores de qualidade

### Requirement: Página sobre e metodologia
O site SHALL ter uma página estática que descreve as fontes de dados, a definição de cada indicador (incidência, média móvel, nível de alerta) e a data da última atualização dos dados.

#### Scenario: Data de atualização
- **WHEN** a página sobre é aberta
- **THEN** ela exibe a data da geração mais recente das tabelas gold

### Requirement: Filtros na URL
Os filtros de ano, país e região SHALL ser representados no caminho ou na query string, de modo que abrir a mesma URL reproduza a mesma visão. Valores inválidos SHALL voltar ao padrão, sem erro.

#### Scenario: Link compartilhado
- **WHEN** alguém abre a URL da página do Brasil com `?ano=2024`
- **THEN** a página é renderizada com os dados de 2024

#### Scenario: Ano inválido
- **WHEN** a URL traz `?ano=abc` ou um ano sem dados
- **THEN** a página usa o ano mais recente com dados e indica o ano exibido

### Requirement: Gráficos e mapas interativos como melhoria progressiva
Gráficos e mapas SHALL ter interação no navegador (tooltip com valor exato, destaque ao passar o mouse e clique no mapa para navegar), e o JavaScript deles SHALL ser carregado só nas páginas que os exibem. Sem JavaScript, a página SHALL continuar mostrando os mesmos números em tabela.

#### Scenario: Clique no mapa
- **WHEN** o usuário clica em um país no mapa do panorama
- **THEN** o navegador abre a página desse país mantendo o ano selecionado

#### Scenario: Página sem gráficos
- **WHEN** a página sobre é carregada
- **THEN** nenhum JavaScript de gráfico ou mapa é baixado

### Requirement: Backend indisponível ou dado ausente
Se o backend falhar ou demorar além do tempo limite configurado, a página SHALL responder com estado de erro amigável e HTTP 503. Seções sem dados para o filtro SHALL mostrar a mensagem "sem dados para o período" em vez de gráficos vazios ou quebrados.

#### Scenario: Backend fora do ar
- **WHEN** o backend não responde dentro do tempo limite
- **THEN** o site responde HTTP 503 com uma mensagem de indisponibilidade temporária

#### Scenario: Seção sem dados
- **WHEN** o ranking de regiões de um país não tem linhas para o ano selecionado
- **THEN** a seção exibe "sem dados para o período" e o restante da página é exibido normalmente

### Requirement: Cache HTTP das páginas
As respostas das páginas SHALL incluir cabeçalhos de cache com validade curta e configurável, e os assets com hash no nome SHALL ser servidos com cache longo e imutável.

#### Scenario: Asset do build
- **WHEN** o navegador baixa um arquivo JavaScript ou CSS gerado pelo build
- **THEN** a resposta tem `Cache-Control` com `immutable` e validade de pelo menos 7 dias

### Requirement: Acessibilidade e responsividade
As páginas SHALL ser utilizáveis em telas a partir de 360 px de largura sem rolagem horizontal. Gráficos e mapas SHALL ter alternativa textual em tabela, e as páginas SHALL ter `lang="pt-BR"`, títulos e descrições próprios.

#### Scenario: Celular
- **WHEN** a página de um país é aberta numa tela de 360 px
- **THEN** todo o conteúdo cabe na largura, sem rolagem horizontal

### Requirement: Health check do servidor web
O servidor web SHALL expor uma rota de health check que responde HTTP 200 quando o processo está pronto, sem depender da disponibilidade do backend.

#### Scenario: Backend fora do ar
- **WHEN** o backend está indisponível e o health check do site é chamado
- **THEN** a resposta é HTTP 200
