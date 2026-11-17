# Spec Delta

## Purpose

Publicar o Atlas Epidemiológico da Dengue como site público, renderizado no servidor. Uma página inicial reúne todas as seções e cada seção abre uma página de detalhe com os indicadores das tabelas gold. Qualquer visão pode ser compartilhada por link.

## ADDED Requirements

### Requirement: Página inicial com todas as seções
A página inicial SHALL listar todas as seções do site, cada uma com título, descrição curta e link para a sua página de detalhe. Seções disponíveis SHALL mostrar um número de destaque calculado a partir dos dados atuais. Seções planejadas e ainda não disponíveis SHALL aparecer marcadas como "em breve", sem link. A lista de seções da página inicial e a navegação do cabeçalho SHALL ser sempre a mesma.

#### Scenario: Entrada no site
- **WHEN** a página inicial é aberta
- **THEN** aparecem os cartões "Série histórica", "Mapa por UF" e "Sobre", cada um com link para a sua página
- **AND** os cartões "Previsão" e "Qualidade dos dados" aparecem como "em breve" e sem link

#### Scenario: Navegação a partir de uma seção
- **WHEN** o usuário está numa página de seção
- **THEN** o cabeçalho mostra as mesmas seções da página inicial, com a seção atual destacada
- **AND** uma trilha "Início › <seção>" leva de volta à página inicial

### Requirement: Série histórica dos casos
A página de série histórica SHALL mostrar os casos prováveis de dengue por semana epidemiológica, do início da série (2000) até a semana mais recente disponível, para o Brasil ou para uma UF escolhida. A página SHALL mostrar também:
- o total de casos do ano epidemiológico mais recente;
- os casos da semana mais recente;
- a variação em relação à mesma semana do ano anterior;
- a data da última atualização dos dados.

#### Scenario: Brasil
- **WHEN** a página de série histórica é aberta sem parâmetros
- **THEN** a série exibida é a do Brasil, da primeira à última semana disponível

#### Scenario: UF escolhida
- **WHEN** a página é aberta com `?uf=SP`
- **THEN** a série e os indicadores exibidos são os de São Paulo
- **AND** o seletor de UF mostra São Paulo selecionado

#### Scenario: UF inválida
- **WHEN** a página é aberta com `?uf=XX`
- **THEN** a página mostra a série do Brasil e indica que a UF pedida não existe

### Requirement: Mapa por UF
A página do mapa SHALL mostrar a incidência de casos prováveis por 100 mil habitantes de cada UF no ano epidemiológico escolhido, num mapa coroplético com legenda de faixas. Ao lado do mapa, SHALL aparecer o ranking das UFs pela incidência. O clique numa UF SHALL abrir a série histórica dessa UF.

#### Scenario: Ano padrão
- **WHEN** a página do mapa é aberta sem parâmetros
- **THEN** o ano exibido é o ano epidemiológico mais recente com dados, e a página indica se o ano ainda está em andamento

#### Scenario: Clique numa UF
- **WHEN** o usuário clica em Minas Gerais no mapa
- **THEN** o navegador abre a série histórica com `?uf=MG`

### Requirement: Página sobre e metodologia
O site SHALL ter uma página estática com as fontes de dados, a definição de cada indicador (caso provável, incidência, semana epidemiológica) e a data da geração mais recente dos dados.

#### Scenario: Data de atualização
- **WHEN** a página sobre é aberta
- **THEN** ela exibe a data da geração mais recente das tabelas gold usadas pelo site

### Requirement: Elementos reutilizados com aparência e comportamento únicos
Um elemento de interface que aparece em mais de uma página SHALL ter a mesma aparência e o mesmo comportamento em todas elas. Esses elementos são cabeçalho, rodapé, cartão de seção, indicadores, filtros, gráfico, mapa, ranking, mensagem de erro e mensagem de "sem dados". O visual SHALL seguir o design system "Painel":
- fundo claro com conteúdo em folhas brancas;
- bloco de destaque azul com texto branco;
- indicadores em caixa alta.

#### Scenario: Mesmo indicador em duas páginas
- **WHEN** os casos da semana mais recente aparecem na página inicial e na série histórica
- **THEN** o valor, o formato numérico e o estilo são os mesmos nas duas páginas

### Requirement: Renderização no servidor a partir do backend
Cada página SHALL ser renderizada no servidor com os dados obtidos das rotas `/gold/*` do backend, e o HTML entregue SHALL já conter os indicadores principais da página, sem depender de JavaScript no navegador.

#### Scenario: Página aberta sem JavaScript
- **WHEN** a série histórica é aberta com JavaScript desabilitado
- **THEN** o HTML exibe os indicadores e uma tabela com os totais por ano e as semanas mais recentes

### Requirement: Backend acessível apenas pelo servidor web
O navegador SHALL se comunicar somente com o domínio do site. A URL do backend SHALL ser lida de variável de ambiente do servidor em runtime e SHALL NOT aparecer no HTML ou no JavaScript enviados ao navegador.

#### Scenario: Troca da URL do backend
- **WHEN** o container do site é reiniciado com outro valor na variável de URL do backend
- **THEN** as páginas passam a usar o novo backend sem rebuild da imagem
- **AND** nenhum recurso enviado ao navegador contém essa URL

### Requirement: Filtros na URL
Os filtros de UF e de ano SHALL ficar na query string, de modo que abrir a mesma URL reproduza a mesma visão. Os filtros SHALL funcionar sem JavaScript, com envio de formulário. Valores inválidos SHALL voltar ao padrão, sem erro.

#### Scenario: Link compartilhado
- **WHEN** alguém abre `/mapa?ano=2024`
- **THEN** o mapa é renderizado com os dados de 2024

#### Scenario: Ano inválido
- **WHEN** a URL traz `?ano=abc` ou um ano sem dados
- **THEN** a página usa o ano mais recente com dados e indica o ano exibido

### Requirement: Gráficos e mapa interativos como melhoria progressiva
Gráficos e mapa SHALL ter interação no navegador:
- tooltip com o valor exato;
- destaque ao passar o mouse;
- zoom no período da série;
- clique no mapa para navegar.

O JavaScript deles SHALL ser carregado só nas páginas que os exibem. Sem JavaScript, a página SHALL continuar mostrando os números em tabela.

#### Scenario: Zoom na série
- **WHEN** o usuário seleciona um intervalo de anos no controle de zoom da série histórica
- **THEN** o gráfico mostra só as semanas desse intervalo, com o eixo ajustado

#### Scenario: Página sem gráficos
- **WHEN** a página sobre é carregada
- **THEN** nenhum JavaScript de gráfico ou mapa é baixado

### Requirement: Backend indisponível ou dado ausente
Se o backend falhar ou demorar além do tempo limite configurado, a página SHALL responder com estado de erro amigável e HTTP 503. A página inicial SHALL continuar exibindo os cartões das seções, só sem os números de destaque. Seções sem dados para o filtro SHALL mostrar a mensagem "sem dados para o período" em vez de gráficos vazios ou quebrados.

#### Scenario: Backend fora do ar numa seção
- **WHEN** o backend não responde dentro do tempo limite na página do mapa
- **THEN** o site responde HTTP 503 com uma mensagem de indisponibilidade temporária

#### Scenario: Backend fora do ar na página inicial
- **WHEN** o backend não responde na abertura da página inicial
- **THEN** os cartões das seções aparecem com os links, sem os números de destaque, e com um aviso de dados indisponíveis

### Requirement: Cache HTTP das páginas
As respostas das páginas SHALL incluir cabeçalhos de cache com validade curta e configurável, e os assets com hash no nome SHALL ser servidos com cache longo e imutável.

#### Scenario: Asset do build
- **WHEN** o navegador baixa um arquivo JavaScript ou CSS gerado pelo build
- **THEN** a resposta tem `Cache-Control` com `immutable` e validade de pelo menos 7 dias

### Requirement: Acessibilidade e responsividade
As páginas SHALL ser utilizáveis em telas a partir de 360 px de largura sem rolagem horizontal. Gráficos e mapa SHALL ter alternativa textual em tabela, e as páginas SHALL ter `lang="pt-BR"`, títulos e descrições próprios.

#### Scenario: Celular
- **WHEN** a página do mapa é aberta numa tela de 360 px
- **THEN** todo o conteúdo cabe na largura, sem rolagem horizontal, com o ranking abaixo do mapa

### Requirement: Health check do servidor web
O servidor web SHALL expor uma rota de health check que responde HTTP 200 quando o processo está pronto, sem depender da disponibilidade do backend.

#### Scenario: Backend fora do ar
- **WHEN** o backend está indisponível e o health check do site é chamado
- **THEN** a resposta é HTTP 200
