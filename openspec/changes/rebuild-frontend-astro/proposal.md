# Proposal

## Why

O front atual (Vite + React, servido estático pelo nginx) depende de uma URL de API embutida no build e foi construído sobre dados mockados que depois foram trocados pelos reais. Para o novo `atlas_epidemiologia`, o site será refeito do zero em **Astro** (já iniciado em `frontend/` com o template *basics*). A renderização no servidor deixa as páginas leves, indexáveis e com a URL do backend restrita ao servidor.

## What Changes

- Novo site público "Atlas Epidemiológico da Dengue" em Astro com **SSR (adapter Node)**. As páginas são renderizadas no servidor a partir das rotas `/gold/*` do backend.
- Conjunto inicial de páginas, proposto a partir dos dados gold disponíveis e **a confirmar pelo usuário**:
  - panorama da América do Sul;
  - página por país;
  - detalhe por região (admin1), com municípios no Brasil e departamentos na Argentina;
  - qualidade dos dados;
  - sobre e metodologia.
- Filtros (ano, país, região) representados na URL por query string, para que qualquer visão possa ser compartilhada por link e funcione sem JavaScript.
- Gráficos e mapas interativos como ilhas no cliente, com JavaScript carregado só nas páginas que os usam.
- O navegador fala apenas com o servidor do Astro. O servidor chama o backend pela URL interna configurada em runtime, então não existe mais URL de API embutida no build.
- Nova imagem `atlas-epidemiologia-frontend` (Node) no lugar da imagem nginx.
- **BREAKING** em relação ao front antigo: as telas, os componentes React e o chat com agente não são migrados.
- **Substitui**, na mudança `decouple-architecture-bigquery`, o grupo de tarefas 6 (cópia do front React) e o requisito "Frontend configurável em runtime" da capability `container-delivery`. Aquela mudança deve ser ajustada com `openspec-update-change`.

## Capabilities

### New Capabilities
- `atlas-web`: o site público, com as páginas, a navegação, os filtros por URL, a visualização de séries e mapas, os estados de erro e de dados ausentes, e a configuração de runtime do servidor web.

### Modified Capabilities
<!-- Nenhuma spec principal existe ainda em openspec/specs/. O requisito de front em runtime vive apenas na mudança decouple-architecture-bigquery, ainda não arquivada. -->

## Impact

- **Código**: `frontend/` passa do template *basics* para o site completo. Entram `@astrojs/node`, uma biblioteca de gráficos e mapas, e os GeoJSON reaproveitados de `projeto_epidemiologia/front/public/geo/`, que são dados e não componentes.
- **Backend**: nenhuma mudança de contrato. O front consome as rotas `/gold/*` existentes.
- **Deploy**: o serviço `frontend` da stack `atlas-app` passa a ser um container Node com uma variável de URL interna do backend. Expor publicamente o `api.dengue.contovisual.com.br` deixa de ser necessário para o site; essa decisão fica para a `decouple-architecture-bigquery`.
- **CI**: o workflow do frontend passa a rodar `astro check` e `astro build` e a publicar a imagem Node.
- **Fora de escopo**: chat/agente, autenticação, internacionalização (o site sai só em pt-BR), novas tabelas gold e conteúdo do modelo de AI.
