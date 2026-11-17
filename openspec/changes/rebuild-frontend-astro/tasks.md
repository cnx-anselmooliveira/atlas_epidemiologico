# Tasks

## 1. Pré-requisitos: dados e backend

- [x] 1.1 Criar a gold `gold_dengue_casos_provaveis_brasil_semanal` (soma das 27 UFs por semana a partir de `gold_dengue_casos_provaveis_uf_semanal`, população e incidência do Brasil, `gold_generated_at`) com `.yml` e testes (`unique` em `week_start`, `not_null`, total igual à soma das UFs); verificar com `dbt build --select gold_dengue_casos_provaveis_brasil_semanal` e conferindo que o grupo `gold` da `process_etl_atlas` passa a ter a tarefa do model
- [x] 1.2 Atualizar a mudança `decouple-architecture-bigquery` via `openspec-update-change`: incluir as rotas `GET /gold/casos-provaveis-brasil-semanal` e `GET /gold/casos-provaveis-uf-semanal` (filtros `uf`, `epi_year`), remover o grupo 6 (front React), substituir o requisito "Frontend configurável em runtime" de `container-delivery` e alinhar o caminho do dbt (`airflow/dags/utfpr_dengue/`); verificar com `openspec validate decouple-architecture-bigquery --strict`
- [ ] 1.3 Implementar o backend (grupo 5 da `decouple-architecture-bigquery`) até as duas rotas responderem localmente com dados reais; verificar com `curl` em `/gold/casos-provaveis-uf-semanal?uf=SP&limit=5` e `/gold/casos-provaveis-brasil-semanal?limit=5`

## 2. Base do projeto Astro

- [ ] 2.1 Remover o conteúdo do template (`Welcome.astro`, `src/assets/*`, "Astro Basics") e definir `name: atlas-epidemiologia-frontend` no `package.json`; verificar que `npm run build` passa
- [ ] 2.2 Instalar `@astrojs/node` compatível com o Astro instalado e configurar `output: 'server'` + `adapter: node({ mode: 'standalone' })`; verificar que `npm run build` gera `dist/server/entry.mjs` e que `node dist/server/entry.mjs` responde na porta 4321
- [ ] 2.3 Declarar o schema `astro:env` (`API_INTERNAL_URL` server/secret, `BACKEND_TIMEOUT_MS`, `PAGE_CACHE_SECONDS`, `PUBLIC_SITE_URL`) e um `.env.example`; verificar que o servidor falha na inicialização sem `API_INTERNAL_URL` e que `grep` em `dist/client` não encontra o valor usado no build
- [ ] 2.4 Adicionar Vitest, Playwright, ESLint (com `no-restricted-imports` bloqueando `src/lib/server/*` em scripts de cliente) e os scripts `check` (`astro check`), `test`, `test:e2e`, `lint`; verificar que todos rodam em verde no projeto vazio

## 3. Camada de dados e mock

- [ ] 3.1 Criar `mock-backend/` (servidor Node sem dependências) com as duas rotas, filtros por igualdade, `limit/offset`, flags de atraso e 503, e fixtures coerentes (3 anos, 4 UFs e o Brasil, com o ano mais recente incompleto); verificar com um teste Vitest do próprio mock
- [ ] 3.2 Implementar `src/lib/server/gold.ts` (tipos das duas golds, uma função por rota, paginação até esgotar, timeout e `BackendUnavailableError`); verificar com testes Vitest de paginação (2 páginas), timeout e 5xx
- [ ] 3.3 Implementar `src/lib/series.ts` (totais por ano, última semana × mesma semana do ano anterior, incidência por UF no ano, ano em andamento), `src/lib/filtros.ts` (`parseUf`, `parseAno`) e `src/lib/format.ts` (inteiro, taxa por 100 mil, variação %, data pt-BR); verificar com testes Vitest, incluindo `?uf=XX`, `?ano=abc` e ano fora da faixa
- [ ] 3.4 Criar `src/data/secoes.ts` (Série histórica, Mapa por UF e Sobre disponíveis; Previsão e Qualidade dos dados em breve) e `src/data/ufs.ts` (sigla, nome, região); verificar com teste Vitest que toda seção disponível tem página em `src/pages/`
- [ ] 3.5 Adicionar `npm run dev:mock` (mock + `astro dev` apontando para ele); verificar que a página inicial abre com dados das fixtures

## 4. Design system e layout

- [ ] 4.1 Copiar de `frontend/design-system/status_invest/` só o necessário para `src/styles/ds/` (tokens e CSS, com `index.css` de entrada) e `src/scripts/ds/` (`ds.js`, `echarts-theme.js`), e `icons.svg` para `public/`, com cabeçalho de origem em cada arquivo e sem vitrine, README ou menções à referência; trocar o `@import` de fontes por `@fontsource/source-sans-3`, `source-serif-4` e `source-code-pro`; verificar com `git status` (arquivos novos versionados, nada de `design-system/`) e `grep -ri "status invest" src public` vazio
- [ ] 4.2 Criar `BaseLayout.astro` (`lang="pt-BR"`, título e descrição por página, canonical a partir de `PUBLIC_SITE_URL`, CSS do DS, tema salvo aplicado inline no `<head>`, `initDesignSystem()`), `SiteHeader.astro` (navegação de `secoes.ts`, seção atual destacada), `SiteFooter.astro` e `PageHeader.astro` (trilha "Início › Seção"); verificar com `astro check` e teste da Container API (seção atual com `aria-current`)

## 5. Componentes

- [ ] 5.1 Criar `SectionCard.astro` (disponível com link e destaque opcional; "em breve" sem link), `KpiStrip.astro`/`KpiCard.astro` (primeiro no bloco azul, variação com seta), `EmptyState.astro`, `BackendError.astro` e `SourceNote.astro`; verificar com testes da Container API
- [ ] 5.2 Criar `FilterForm.astro` com `UfSelect` e `YearSelect` (form GET, funciona sem JS, valor atual selecionado) e `DataTable.astro`; verificar com testes da Container API
- [ ] 5.3 Instalar `echarts` e criar `TimeSeriesChart.astro` (figura, `DataTable` resumida, JSON embutido, `<script>` com `echarts/core` tree-shaken, `mountChart`, `dataZoom` começando nos últimos 5 anos, tooltip com semana e data); verificar com teste da Container API (tabela presente) e manualmente o zoom e o tooltip no navegador
- [ ] 5.4 Copiar `brasil-uf.json` de `projeto_epidemiologia/front/public/geo/` para `public/geo/` e criar `ChoroplethMap.astro` (registerMap, faixas `--viz-map-1..6`, legenda, tooltip, clique → `/serie-historica?uf=<sigla>`, tabela alternativa) e `RankingBars.astro`; verificar com teste da Container API e manualmente o clique

## 6. Páginas

- [ ] 6.1 Implementar `/` (apresentação + um `SectionCard` por seção, destaques: casos na semana mais recente e UF com maior incidência no ano; backend fora → cartões sem destaque e aviso); verificar com testes da Container API com o mock normal e em modo 503
- [ ] 6.2 Implementar `/serie-historica` (`?uf=`, KPIs, série, tabela por ano, `SourceNote`; UF inválida → Brasil com aviso); verificar com testes da Container API para Brasil, `SP` e `XX`
- [ ] 6.3 Implementar `/mapa` (`?ano=`, KPIs, mapa + ranking, indicação de ano em andamento; ano inválido → mais recente); verificar com testes da Container API para o ano padrão, `2024` e `abc`
- [ ] 6.4 Implementar `/sobre` (fontes, definições, data da gold mais recente), `/healthz`, `404.astro`, `500.astro` e o tratamento de `BackendUnavailableError` → 503 nas páginas de seção; implementar `src/middleware.ts` (`Cache-Control` das páginas e de `/geo/*`; conferir `/_astro/*` no build standalone e cobri-lo se não vier `immutable`); verificar com testes da Container API (503 com o mock em erro, `/healthz` 200 com o mock desligado) e `curl -I` numa página, num asset e no GeoJSON

## 7. Testes de ponta a ponta e validação real

- [ ] 7.1 Escrever o smoke Playwright contra o build de produção + mock: sem rolagem horizontal a 360 px em `/`, `/serie-historica` e `/mapa`; série com JS desabilitado mostra KPIs e tabela; clique numa UF do mapa abre a série dela; `/sobre` não baixa chunks do ECharts; verificar com `npm run test:e2e` em verde
- [ ] 7.2 Rodar o site contra o backend real local e conferir os números com o BigQuery (total do Brasil no ano mais recente, casos de SP na última semana, incidência de uma UF no mapa); verificar registrando as três comparações no PR

## 8. Imagem, CI e deploy

- [ ] 8.1 Criar `frontend/Dockerfile` multi-stage `node:22-alpine` (usuário `node`, `HOST=0.0.0.0`, `PORT=4321`, `HEALTHCHECK` em `/healthz`) e `.dockerignore` (excluindo `design-system/`); verificar `docker build` e `docker run -e API_INTERNAL_URL=…` servindo `/` com dados
- [ ] 8.2 Criar `.github/workflows/frontend.yml` (paths `frontend/**`): `npm ci`, `lint`, `check`, `test`, `test:e2e`, build da imagem; em `main` publicar `anselmomendes/atlas-epidemiologia-frontend:{sha7,latest}` e chamar o webhook do Portainer com `?tag=`; verificar com um PR (sem push) e um push em `main`
- [ ] 8.3 Ajustar o serviço `frontend` em `deploy/app.stack.yml` (imagem Node, porta Traefik 4321, `API_INTERNAL_URL=http://backend:8000`, redes pública e interna); verificar com `docker stack config` e, no host temporário, as páginas renderizando com dados reais
- [ ] 8.4 Reescrever `frontend/README.md` (hierarquia, componentes, design system copiado, variáveis, `dev:mock`, testes, imagem) e manter `AGENTS.md` coerente; verificar seguindo o passo a passo do README numa cópia limpa

## Workflow follow-up

- Arquivar a mudança após o corte para `dengue.contovisual.com.br`.
- As seções "em breve" (Previsão, Qualidade dos dados) viram mudanças próprias.
