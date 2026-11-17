# Proposal

## Why

O front antigo (Vite + React, servido estático pelo nginx) depende de uma URL de API embutida no build e foi construído sobre dados mockados que depois foram trocados pelos reais. Para o `atlas_epidemiologia`, o site será refeito do zero em **Astro** (já iniciado em `frontend/` com o template *basics*). A renderização no servidor deixa as páginas leves e indexáveis, e a URL do backend fica restrita ao servidor.

O dado que está pronto e validado hoje é a gold `gold_dengue_casos_provaveis_uf_semanal`, com casos prováveis do Brasil por UF e semana desde 2000. Por isso o site começa pelo Brasil, com uma página inicial que reúne tudo o que o site oferece e uma página de detalhe para cada seção.

## What Changes

- Novo site público "Atlas Epidemiológico da Dengue" em Astro com **SSR (adapter Node)**. As páginas são renderizadas no servidor a partir das rotas `/gold/*` do backend.
- **Hierarquia do site**:
  - a página inicial (`/`) mostra todas as seções do site, cada uma num cartão com título, descrição, um número de destaque e o link para a página de detalhe;
  - cada seção tem a sua página;
  - seções planejadas e ainda não feitas aparecem como "em breve", sem link.
- **Seções da primeira versão**:
  - **Série histórica** (`/serie-historica`): casos prováveis por semana epidemiológica, de 2000 até a semana mais recente, para o Brasil ou para uma UF;
  - **Mapa por UF** (`/mapa`): incidência por 100 mil habitantes de cada UF no ano escolhido, com ranking das UFs. O clique numa UF abre a série histórica dela;
  - **Sobre**: fontes, definições e data da última atualização dos dados.
- **Em breve** (só o cartão na página inicial): previsão dos modelos e qualidade dos dados.
- **Componentes Astro para todo elemento reutilizado**. Cabeçalho, rodapé, cartão de seção, faixa de indicadores, filtros, gráfico de série, mapa, ranking e estados de erro e de vazio são componentes. As páginas só compõem esses componentes e o layout próprio da página.
- **Visual do design system "Painel"**:
  - a referência fica local em `frontend/design-system/status_invest/`, que é ignorada pelo Git e só é consultada;
  - o site leva uma **cópia versionada** só dos tokens, do CSS e do JS que usa, sem a vitrine e sem a documentação da referência.
- Filtros (UF, ano) na query string, para que qualquer visão possa ser compartilhada por link e funcione sem JavaScript.
- Gráficos e mapa interativos como ilhas no cliente, com JavaScript carregado só nas páginas que os usam.
- O navegador fala apenas com o servidor do Astro. O servidor chama o backend pela URL interna configurada em runtime.
- **Pré-requisito: o backend vem antes.**
  - A API gold (`decouple-architecture-bigquery`, grupo 5) precisa existir e servir as rotas desta mudança.
  - Entra também uma gold nacional nova, `gold_dengue_casos_provaveis_brasil_semanal`, para a série do Brasil.
- Nova imagem `atlas-epidemiologia-frontend` (Node) no lugar da imagem nginx.
- **BREAKING** em relação ao front antigo:
  - as telas, os componentes React e o chat com agente não são migrados;
  - o panorama da América do Sul e as páginas por país e região saem do escopo desta versão.
- **Substitui**, na mudança `decouple-architecture-bigquery`, o grupo de tarefas 6 (cópia do front React) e o requisito "Frontend configurável em runtime" da capability `container-delivery`. Aquela mudança deve ser ajustada com `openspec-update-change`, incluindo as rotas novas do backend.

## Capabilities

### New Capabilities
- `atlas-web`: o site público. Cobre:
  - a hierarquia (página inicial e páginas de seção);
  - a série histórica e o mapa por UF;
  - os filtros por URL;
  - os estados de erro e de dados ausentes;
  - a configuração de runtime do servidor web.

### Modified Capabilities
<!-- Nenhuma spec principal existe ainda em openspec/specs/. O requisito de front em runtime vive apenas na mudança decouple-architecture-bigquery, ainda não arquivada. -->

## Impact

- **Código**:
  - `frontend/` passa do template *basics* para o site;
  - entram `@astrojs/node`, `echarts`, a cópia versionada do design system (`frontend/src/styles/`, `frontend/src/scripts/ds/`) e o GeoJSON das UFs (`brasil-uf.json`, reaproveitado do projeto antigo como dado).
- **dbt**: nova gold `gold_dengue_casos_provaveis_brasil_semanal`, uma linha por semana, soma das UFs, com população e incidência do Brasil.
- **Backend**:
  - depende da API gold da `decouple-architecture-bigquery`;
  - precisa das rotas da gold por UF e da gold nacional, que não existiam na API antiga.
- **Deploy**: o serviço `frontend` da stack `atlas-app` passa a ser um container Node com uma variável de URL interna do backend.
- **CI**: o workflow do frontend passa a rodar `astro check` e `astro build` e a publicar a imagem Node. Como o design system usado está versionado, o CI não depende da pasta local.
- **Fora de escopo**:
  - chat/agente, autenticação e internacionalização (o site sai só em pt-BR);
  - os países da América do Sul e as páginas das seções "em breve";
  - o conteúdo dos modelos de previsão.
