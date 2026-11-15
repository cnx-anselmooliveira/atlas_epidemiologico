# Tasks

## 1. Base do projeto Astro

- [ ] 1.1 Remover o conteúdo do template (`Welcome.astro`, `src/assets/*`, "Astro Basics") e definir `name: atlas-epidemiologia-frontend` no `package.json`; verificar que `npm run build` passa
- [ ] 1.2 Instalar `@astrojs/node` compatível com o Astro instalado e configurar `output: 'server'` + `adapter: node({ mode: 'standalone' })`; verificar que `npm run build` gera `dist/server/entry.mjs` e que `node dist/server/entry.mjs` responde na porta 4321
- [ ] 1.3 Declarar o schema `astro:env` (`API_INTERNAL_URL` server/secret, `BACKEND_TIMEOUT_MS`, `PAGE_CACHE_SECONDS`, `PUBLIC_SITE_URL`) e um `.env.example`; verificar que o servidor falha na inicialização sem `API_INTERNAL_URL` e que `grep` em `dist/client` não encontra o valor usado no build
- [ ] 1.4 Adicionar Vitest, Playwright, ESLint (com `no-restricted-imports` bloqueando `src/lib/server/*` em scripts de cliente) e os scripts `check` (`astro check`), `test`, `test:e2e`, `lint`; verificar que todos rodam em verde no projeto vazio

## 2. Backend mock e camada de dados

- [ ] 2.1 Criar `mock-backend/` (servidor Node sem dependências) servindo `GET /gold/*` com filtros por igualdade, `limit/offset` e flags de atraso e 503; adicionar fixtures pequenas e coerentes (2 anos, 3 países incluindo BRA e ARG, algumas UFs, municípios e departamentos); verificar com um teste Vitest do próprio mock
- [ ] 2.2 Adicionar `npm run dev:mock` (mock + `astro dev` apontando para ele); verificar que a página inicial abre com dados das fixtures
- [ ] 2.3 Implementar `src/lib/server/gold.ts` com tipos das respostas, uma função por rota usada, paginação até esgotar, timeout e `BackendUnavailableError`; verificar com testes Vitest de paginação (2 páginas), timeout e 5xx
- [ ] 2.4 Implementar utilitários `parseAno`, `slugifyRegiao`/lookup slug → nome e formatadores pt-BR (inteiro, taxa por 100 mil, variação %); verificar com testes Vitest, incluindo `?ano=abc` e ano fora da faixa

## 3. Layout, estilo e componentes de visualização

- [ ] 3.1 Integrar o Atlas DS (`frontend/design-system/`): importar `css/atlas.css` no `BaseLayout.astro`, trocar o `@import` do Google Fonts por `@fontsource/ibm-plex-sans`/`ibm-plex-mono`, copiar `icons/icons.svg` para `public/`, aplicar o tema salvo inline no `<head>` e chamar `initDesignSystem()`; criar o `BaseLayout.astro` (`lang="pt-BR"`, `<title>`/description por página, canonical a partir de `PUBLIC_SITE_URL`, cabeçalho com navegação, rodapé com fontes); verificar com `astro check` e inspeção do HTML
- [ ] 3.2 Criar `KpiCard.astro`, `YearSelect.astro` (form GET com `?ano=`, funciona sem JS), `EmptyState.astro` ("sem dados para o período") e `BackendError.astro`; verificar com testes da Container API
- [ ] 3.3 Instalar `echarts` e criar `EpiCurve.astro` (casos semanais, média móvel 3 semanas, mesma semana do ano anterior) com figura, tabela alternativa, JSON embutido e `<script>` importando `echarts/core` com tree-shaking; verificar com teste da Container API (tabela presente) e manualmente o tooltip no navegador
- [ ] 3.4 Criar `AlertStrip.astro` (nível de alerta das semanas recentes com legenda) e `RankingBars.astro` (ranking de regiões), ambos com tabela alternativa; verificar com testes da Container API
- [ ] 3.5 Copiar os GeoJSON de `projeto_epidemiologia/front/public/geo/` para `public/geo/`, simplificando os arquivos acima de 1 MB; criar `ChoroplethMap.astro` (registerMap, escala sequencial, tooltip, clique navegando com `?ano=` preservado, tabela alternativa); verificar o tamanho dos arquivos com `du` e o clique manualmente

## 4. Páginas

- [ ] 4.1 Implementar `/` (KPIs por país do ano, mapa da América do Sul, curva semanal agregada; ano padrão = mais recente com dados); verificar com teste da Container API contra as fixtures
- [ ] 4.2 Implementar `/pais/[iso3]` (curva, alerta, incidência, ranking de admin1; 404 para país sem dados); verificar com testes da Container API para `BRA` e para um código inexistente (status 404)
- [ ] 4.3 Implementar `/pais/[iso3]/[regiao]` (curva da região; mapa e ranking de municípios para BRA e de departamentos para ARG; sem seção de nível inferior nos demais; 404 para slug desconhecido); verificar com testes da Container API para UF do Brasil, província da Argentina e região de outro país
- [ ] 4.4 Implementar `/qualidade-dos-dados`, `/sobre` (com data da geração gold mais recente), `/healthz`, `404.astro` e `500.astro`, além do tratamento de `BackendUnavailableError` → 503 em todas as páginas de dados; verificar com testes da Container API (503 com o mock em modo erro, `/healthz` 200 com o mock desligado)
- [ ] 4.5 Implementar `src/middleware.ts` com `Cache-Control` das páginas (`max-age=PAGE_CACHE_SECONDS` em 200, `no-store` em 4xx/5xx) e de `/geo/*`; conferir o cabeçalho de `/_astro/*` no build standalone e cobri-lo no middleware se não vier `immutable`; verificar com `curl -I` em uma página, um asset e um GeoJSON

## 5. Testes de ponta a ponta

- [ ] 5.1 Escrever o smoke Playwright contra o build de produção + mock: sem overflow horizontal a 360 px em `/`, `/pais/BRA` e `/pais/BRA/<uf>`; `/pais/BRA` com JS desabilitado mostra KPIs e tabela; clique no mapa do panorama abre o país com `?ano=` preservado; `/sobre` não baixa chunks do ECharts; verificar com `npm run test:e2e` em verde

## 6. Imagem, CI e deploy

- [ ] 6.1 Criar `frontend/Dockerfile` multi-stage `node:22-alpine` (usuário `node`, `HOST=0.0.0.0`, `PORT=4321`, `HEALTHCHECK` em `/healthz`) e `.dockerignore`; verificar `docker build` e `docker run -e API_INTERNAL_URL=http://host.docker.internal:<porta-mock>` servindo `/` com dados
- [ ] 6.2 Criar ou ajustar `.github/workflows/frontend.yml` (paths `frontend/**`): `npm ci`, `lint`, `check`, `test`, `test:e2e`, build da imagem; em `main` publicar `anselmomendes/atlas-epidemiologia-frontend:{sha7,latest}` e chamar o webhook do Portainer com `?tag=`; verificar com um PR (sem push) e um push em `main`
- [ ] 6.3 Ajustar o serviço `frontend` em `deploy/app.stack.yml` (imagem Node, porta Traefik 4321, `API_INTERNAL_URL=http://backend:8000`, redes pública e interna); verificar com `docker stack config` e, no host temporário, as páginas renderizando com dados reais
- [ ] 6.4 Reescrever `frontend/README.md` (stack, variáveis, `dev:mock`, testes, build da imagem) e manter `AGENTS.md` coerente; verificar seguindo o passo a passo do README numa cópia limpa

## 7. Integração com a mudança de arquitetura

- [ ] 7.1 Atualizar a mudança `decouple-architecture-bigquery` via `openspec-update-change`: remover o grupo 6 (front React), substituir o requisito "Frontend configurável em runtime" de `container-delivery` e alinhar a stack (`frontend` Node e `API_INTERNAL_URL`); verificar com `openspec validate decouple-architecture-bigquery --strict`
- [ ] 7.2 Validar o site no host temporário contra o backend real (todas as páginas com dados, 503 amigável ao parar o backend, `/healthz` 200); verificar registrando o resultado no PR do corte

## Workflow follow-up

- Confirmar com o usuário o conjunto de páginas proposto antes do apply.
- Arquivar a mudança após o corte para `dengue.contovisual.com.br`.
