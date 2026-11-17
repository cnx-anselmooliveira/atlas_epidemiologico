# Design

## Context

- **Frontend hoje.** `frontend/` contém o template *basics* do `npm create astro@latest`: Astro `^7.4.12`, Node `>=22`, `tsconfig` strict e nenhuma integração. Os arquivos são `index.astro`, `Layout.astro` e `Welcome.astro`.
- **Dados.** A gold `gold_dengue_casos_provaveis_uf_semanal` está no BigQuery: 27 UFs × todas as semanas desde 2000, cerca de 37 mil linhas. Colunas usadas:
  - `uf`, `week_start`, `epi_year`, `epi_week`;
  - `probable_cases`, `population`, `incidence`;
  - `gold_generated_at`.
- **Backend.** Ainda não existe. A API gold é o grupo 5 da mudança `decouple-architecture-bigquery`, com:
  - `GET /gold/*` e filtros por igualdade;
  - `limit` de até 1000 e `offset`;
  - Redis como cache;
  - rede interna `backend:8000`.

  As 14 rotas herdadas da API antiga não cobrem a gold por UF, e esta mudança precisa de rotas novas (decisão 3).
- **Design system.** A referência "Painel" está em `frontend/design-system/status_invest/`, que é ignorada pelo Git (`frontend/design-system/`). Ela tem:
  - tokens em custom properties;
  - os CSS `base`, `layout`, `components` e `utilities`;
  - `ds.js` (tema, ondulação, `initDesignSystem`);
  - `echarts-theme.js` (`mountChart`, `buildTheme`, `tooltipHTML`);
  - `icons.svg`.
- **Mapa.** O GeoJSON das UFs (`projeto_epidemiologia/front/public/geo/brasil-uf.json`, 185 KB, 27 feições com `name` = sigla e `fullName`) é reaproveitado como dado.
- A motivação está em proposal.md (Why). Os requisitos estão em `specs/atlas-web/spec.md`.

## Goals / Non-Goals

**Goals:**
- HTML útil sem JavaScript; JavaScript apenas para gráficos e mapa.
- Hierarquia que cresce sem retrabalho: uma seção nova é uma entrada no registro mais uma página.
- Uma imagem que serve qualquer ambiente, configurada só por variáveis de ambiente.
- Testes e CI sem depender do BigQuery, com um backend mock com fixtures.

**Non-Goals:**
- Framework de UI (React, Vue ou Svelte): nenhuma ilha precisa de estado complexo.
- CDN ou cache compartilhado de páginas. O cache de dados fica no Redis do backend.
- Reaproveitar código do front antigo além do GeoJSON.

## Decisions

### 1. SSR com `@astrojs/node` em modo `standalone`
`output: 'server'` e `adapter: node({ mode: 'standalone' })`. O processo Node serve as páginas e os assets de `dist/client`. Foi escolhido em vez de SSG + nginx porque assim a URL do backend fica só no servidor e os dados novos aparecem sem rebuild.

### 2. Configuração em runtime com `astro:env`
O schema em `astro.config.mjs` declara:
- `API_INTERNAL_URL`: `context: 'server'`, `access: 'secret'`;
- `BACKEND_TIMEOUT_MS`, padrão 8000;
- `PAGE_CACHE_SECONDS`, padrão 300;
- `PUBLIC_SITE_URL`, para canonical e OG.

Variáveis `server`/`secret` são lidas em runtime e validadas na inicialização, nunca embutidas no bundle do cliente. Foi descartado ler `process.env` direto, porque não tem validação nem tipos.

### 3. Dados: duas golds, uma rota para cada
Cada visão lê um volume pequeno:

| Visão | Fonte | Linhas |
|---|---|---|
| Série do Brasil | **nova** `gold_dengue_casos_provaveis_brasil_semanal` (soma das 27 UFs por semana, com população e incidência do Brasil) | ~1,4 mil |
| Série de uma UF | `gold_dengue_casos_provaveis_uf_semanal` filtrada por `uf` | ~1,4 mil |
| Mapa de um ano | `gold_dengue_casos_provaveis_uf_semanal` filtrada por `epi_year`, somada por UF no servidor do Astro | ≤ 27 × 53 |
| Destaques da página inicial | a gold nacional (última semana e ano mais recente) | ~1,4 mil (mesma chamada da série) |

As rotas do backend são `GET /gold/casos-provaveis-brasil-semanal` e `GET /gold/casos-provaveis-uf-semanal`, com filtros `uf` e `epi_year`. Elas entram na `decouple-architecture-bigquery` (tarefa 1.2 daqui).

Alternativas descartadas:
- Somar as UFs no front: cerca de 37 mil linhas em 38 páginas da API por visita.
- Rota agregada no backend: foge do contrato "uma rota por tabela gold, só filtros por igualdade".

A gold nacional também serve à previsão nacional no futuro.

### 4. Camada de dados server-only
O módulo `src/lib/server/gold.ts` tem uma função por rota, tipada a partir das colunas acima. As funções usam `fetch` com `AbortSignal.timeout(BACKEND_TIMEOUT_MS)` e um laço de paginação `limit=1000` até receber menos linhas. Uma falha de rede, timeout ou status 5xx lança `BackendUnavailableError`.

As agregações de página (série → totais por ano; ano → incidência por UF; última semana × mesma semana do ano anterior) ficam em `src/lib/series.ts`. São funções puras, testadas com Vitest.

Por estar em `src/lib/server/`, `gold.ts` só é importado em frontmatter de páginas, nunca em `<script>` do cliente. Uma regra ESLint (`no-restricted-imports`) bloqueia o import nos scripts.

### 5. Hierarquia e registro de seções
`src/data/secoes.ts` é a única lista de seções. Cada entrada tem:
- `id`, `titulo`, `descricao` e `href`;
- `status: 'disponivel' | 'em-breve'`;
- `icone`.

A página inicial e o `SiteHeader` leem essa lista, então os dois nunca divergem. Uma seção nova significa uma entrada no registro e um arquivo em `src/pages/`.

| Rota | Conteúdo | Fonte |
|---|---|---|
| `/` | cabeçalho de apresentação + um `SectionCard` por seção, com destaque (casos na semana mais recente, UF com maior incidência no ano) | gold nacional + gold UF do ano |
| `/serie-historica` | `PageHeader`, `FilterForm` (UF), `KpiStrip`, `TimeSeriesChart`, tabela por ano, `SourceNote` | gold nacional ou gold UF (`?uf=`) |
| `/mapa` | `PageHeader`, `FilterForm` (ano), `KpiStrip`, `ChoroplethMap` + `RankingBars`, `SourceNote` | gold UF (`?ano=`) |
| `/sobre` | texto estático + data da gold mais recente | `gold_generated_at` da gold nacional |
| `/healthz` | `GET` sem chamada ao backend | — |

Seções "em breve" na primeira versão: Previsão e Qualidade dos dados. As páginas `404.astro` e `500.astro` também ficam em `src/pages/`.

Validação dos filtros:
- `parseUf` aceita só as 27 siglas, e qualquer outro valor vira "Brasil" com aviso;
- `parseAno` cai no ano mais recente com dados quando o valor é inválido ou está fora da faixa.

### 6. Componentes
A regra é virar componente todo elemento que aparece em mais de uma página ou que encapsula um gráfico. O layout específico de uma página fica na própria página.

| Componente | Uso | Classes do DS |
|---|---|---|
| `BaseLayout` | `<html lang="pt-BR">`, `<head>` (título, descrição, canonical), CSS do DS, tema | — |
| `SiteHeader` / `SiteFooter` | navegação a partir de `secoes.ts`, seção atual destacada; fontes e créditos | `.ds-header`, `.ds-nav`, `.ds-footer` |
| `PageHeader` | trilha "Início › Seção", título, subtítulo | `.ds-section__header` |
| `SectionCard` | cartão da página inicial (disponível ou "em breve") | `.ds-card`, `.ds-badge` |
| `KpiStrip` / `KpiCard` | faixa de indicadores; o primeiro no bloco azul | `.ds-kpi-strip`, `.ds-kpi--on-band`, `.ds-delta` |
| `FilterForm` | formulário GET com `UfSelect` e/ou `YearSelect`, funciona sem JS | `.ds-field`, `.ds-select`, `.ds-btn` |
| `TimeSeriesChart` | série semanal com zoom | `.ds-figure` |
| `ChoroplethMap` | mapa das UFs, faixas de incidência, clique → série | `.ds-figure`, `.ds-legend` |
| `RankingBars` | ranking de UFs | `.ds-rank` |
| `DataTable` | tabela alternativa dos gráficos e tabelas por ano | `.ds-table-wrap`, `.ds-table` |
| `EmptyState` / `BackendError` | "sem dados para o período" e indisponibilidade | `.ds-state` |
| `SourceNote` | fonte (SINAN) e data da gold | `.ds-badge--solid` |

Formatação pt-BR (inteiro, taxa por 100 mil, variação %) fica em `src/lib/format.ts`, usada por todos os componentes.

### 7. Gráficos e mapa com Apache ECharts em `<script>` de componente
`TimeSeriesChart` e `ChoroplethMap` renderizam no servidor:
- uma `<figure>`;
- a `DataTable` com os mesmos dados, que é a alternativa sem JS e acessível;
- um `<script type="application/json">` com a série.

O `<script>` do componente:
- importa `echarts/core` com tree-shaking (`LineChart`, `MapChart`, `DataZoom`, `Tooltip`, `VisualMap`);
- monta o gráfico com o `mountChart()` do design system;
- esconde a tabela visualmente sem tirá-la dos leitores de tela.

O Astro empacota e carrega esse script só nas páginas que usam o componente.

Série:
- 1,4 mil pontos com `dataZoom` (slider), começando nos últimos 5 anos;
- tooltip com semana epidemiológica, data de início e casos.

A tabela alternativa traz os totais por ano e as 12 semanas mais recentes, não as 1,4 mil linhas.

Mapa:
- `echarts.registerMap('brasil-uf', geojson)` com `/geo/brasil-uf.json`;
- `visualMap` em faixas com as classes `--viz-map-1..6` do DS;
- o clique navega para `/serie-historica?uf=<sigla>`.

Alternativas descartadas:
- Chart.js + Leaflet: duas bibliotecas e dois estilos.
- Observable Plot com SVG no servidor: interação limitada e exige jsdom.

### 8. Design system: referência local, cópia versionada
`frontend/design-system/status_invest/` continua só local e só para consulta. O site leva uma **cópia versionada** do que usa:
- `src/styles/ds/`: `tokens.css`, `base.css`, `layout.css`, `components.css`, `utilities.css` e um `index.css` de entrada;
- `src/scripts/ds/`: `ds.js` e `echarts-theme.js`;
- `public/icons.svg`.

O que fica de fora da cópia:
- a vitrine (`index.html`);
- o `README.md`, o `DATAVIZ.md` e o `tokens.json`;
- menções à referência original nos comentários.

O cabeçalho de cada arquivo copiado diz de onde veio. Uma mudança no design system é refeita na referência e copiada de novo.

Fontes Source Sans 3 / Source Serif 4 / Source Code Pro via `@fontsource/*` (sem Google Fonts em runtime). Os componentes só aplicam classes `.ds-*`, a não ser no layout da página. Tailwind foi descartado para manter zero dependências de estilo.

Alternativa descartada: buscar o design system de um bucket no CI. Seriam uma credencial a mais no CI e um build impossível sem rede.

### 9. Cache HTTP
Um middleware (`src/middleware.ts`) define o `Cache-Control`:
- `public, max-age=${PAGE_CACHE_SECONDS}` nas respostas HTML 200;
- `no-store` nas respostas 4xx e 5xx;
- `max-age=604800` em `/geo/*`.

Os assets `/_astro/*` recebem `max-age=31536000, immutable` do servidor standalone. A tarefa 6.4 confere essa suposição; se o standalone não enviar `immutable`, o middleware cobre.

### 10. Backend mock para testes
`frontend/mock-backend/` é um servidor Node mínimo, sem dependências, que serve as duas rotas da decisão 3 a partir de fixtures JSON. Ele:
- aplica os mesmos filtros e a mesma paginação;
- pode simular atraso e erro 503 por query flag.

As fixtures cobrem 3 anos, 4 UFs e o Brasil. `npm run dev:mock` sobe o mock e o `astro dev` apontando para ele. O desenvolvimento do dia a dia usa o backend real (`npm run dev` com `API_INTERNAL_URL`), e o mock serve aos testes e ao CI.

### 11. Testes
- **Vitest**:
  - `parseUf`, `parseAno` e a formatação pt-BR;
  - as agregações de `series.ts`;
  - paginação e timeout de `gold.ts` (com `fetch` mockado).
- **Astro Container API**: renderização dos componentes e das páginas com fixtures. Confere:
  - os cartões e o "em breve" na página inicial;
  - a UF selecionada;
  - o 503 com o backend fora;
  - a página inicial sem destaques quando o backend falha.
- **Playwright** (smoke), contra `astro build && node dist/server/entry.mjs` + mock:
  - 360 px sem rolagem horizontal;
  - série sem JS mostrando a tabela;
  - clique no mapa navegando;
  - `/sobre` sem chunks do ECharts.

### 12. Imagem e deploy
Dockerfile multi-stage `node:22-alpine`:
1. build: `npm ci` e `astro build`;
2. runtime: `npm ci --omit=dev`, `dist/`, usuário `node`, `HOST=0.0.0.0`, `PORT=4321`, `HEALTHCHECK` em `/healthz`, `CMD node ./dist/server/entry.mjs`.

O design system já está versionado em `src/`, então o build não precisa de nada fora do repositório. Na `deploy/app.stack.yml`, o serviço `frontend` recebe `API_INTERNAL_URL=http://backend:8000` e a porta Traefik 4321, nas redes `network_public` e interna.

## Risks / Trade-offs

- [O backend ainda não existe] → é pré-requisito explícito (grupo 1 das tarefas). Com o mock, a base e os componentes podem andar em paralelo, mas as páginas só são aceitas contra o backend real.
- [A cópia do design system diverge da referência] → a cópia é feita uma vez e passa a ser a fonte do site. Mudanças futuras na referência são copiadas de novo de propósito, e o cabeçalho de cada arquivo diz de onde veio.
- [A série de 1,4 mil pontos pesa no celular] → `dataZoom` começa nos últimos 5 anos, o renderer é SVG do `mountChart` e a tabela alternativa é resumida.
- [O ano epidemiológico corrente está incompleto e os dados recentes ainda mudam] → o mapa indica "ano em andamento" e a série mostra a data da última atualização (`SourceNote`).
- [Cada página faz chamadas ao backend] → as chamadas de uma página rodam em paralelo (`Promise.all`), o Redis do backend absorve a repetição e as páginas têm `max-age` curto.

## Migration Plan

1. Concluir o backend com as duas rotas e a gold nacional (grupo 1).
2. Desenvolver o site contra o backend local e testar contra o mock.
3. Publicar a imagem pelo CI e subir o serviço `frontend` na stack `atlas-app` em host temporário, junto do backend (`decouple-architecture-bigquery`, grupo 9).
4. Validar contra dados reais e trocar o host para `dengue.contovisual.com.br`.
5. Rollback: voltar a stack antiga (imagem nginx `projeto_epidemiologia_frontend:1.0`).

## Open Questions

- Textos da página "Sobre": créditos do PPGCC/UTFPR e citação dos dados.
