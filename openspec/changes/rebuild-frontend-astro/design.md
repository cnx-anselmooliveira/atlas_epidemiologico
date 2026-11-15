# Design

## Context

- `frontend/` contém o template *basics* do `npm create astro@latest` (Astro `^7.4.12`, Node `>=22`, `tsconfig` strict, sem integrações). Só existem `index.astro`, `Layout.astro` e `Welcome.astro`.
- O backend, definido na mudança `decouple-architecture-bigquery`, expõe `GET /gold/*` com filtros por igualdade, `limit` de até 1000 e `offset`, e roda na rede interna da stack `atlas-app` como `backend:8000`.
- Os GeoJSON do front antigo (`projeto_epidemiologia/front/public/geo/`: América do Sul, admin1 dos 6 países, municípios BR por UF, departamentos AR) são reaproveitados como dados.
- A motivação está em proposal.md (Why). Os requisitos estão em `specs/atlas-web/spec.md`.

## Goals / Non-Goals

**Goals:**
- HTML útil sem JavaScript; JavaScript apenas para gráficos e mapas.
- Uma imagem que serve qualquer ambiente, configurada só por variáveis de ambiente.
- Desenvolvimento do front independente do backend real, usando um backend mock com fixtures.

**Non-Goals:**
- Framework de UI (React, Vue ou Svelte): nenhuma ilha precisa de estado complexo.
- CDN ou cache compartilhado de páginas. O cache de dados fica no Redis do backend.
- Reaproveitar código do front antigo além dos GeoJSON e dos tipos das respostas.

## Decisions

### 1. SSR com `@astrojs/node` em modo `standalone`
`output: 'server'` e `adapter: node({ mode: 'standalone' })`. O processo Node serve as páginas e os assets de `dist/client`. Escolhido pelo usuário em vez de SSG + nginx: assim a URL do backend fica só no servidor e não é preciso gerar `config.js` em runtime.

### 2. Configuração em runtime com `astro:env`
O schema em `astro.config.mjs` declara:
- `API_INTERNAL_URL`: `context: 'server'`, `access: 'secret'`;
- `BACKEND_TIMEOUT_MS`, padrão 8000;
- `PAGE_CACHE_SECONDS`, padrão 300;
- `PUBLIC_SITE_URL`, para canonical e OG.

Variáveis `server`/`secret` são lidas em runtime e validadas na inicialização, nunca embutidas no bundle do cliente. Foi descartado ler `process.env` direto, porque não tem validação nem tipos.

### 3. Camada de dados server-only
O módulo `src/lib/server/gold.ts` tem uma função por rota gold, tipada a partir dos campos atuais. As funções usam `fetch` com `AbortSignal.timeout(BACKEND_TIMEOUT_MS)` e um laço de paginação `limit=1000` até receber menos linhas. Uma falha de rede, timeout ou status 5xx lança `BackendUnavailableError`. Uma página que captura esse erro define `Astro.response.status = 503` e renderiza `<BackendError/>`.

Por estar em `src/lib/server/`, o módulo só é importado em frontmatter de páginas, nunca em `<script>` do cliente. O build verifica isso com uma regra de lint (`no-restricted-imports` nos scripts de cliente).

### 4. Rotas
| Rota | Fonte gold principal |
|---|---|
| `/` | `kpi_country_year`, `epi_curve_weekly` (nível país), `dim_populacao_admin1` |
| `/pais/[iso3]` | `epi_curve_weekly`, `alert_level_weekly`, `incidence_rate_country_weekly`, `top_admin1_ranking` |
| `/pais/[iso3]/[regiao]` | `epi_curve_weekly` (admin1) + `municipio_epi_curve_weekly` (BRA) / `departamento_epi_curve_weekly_argentina` (ARG) + populações |
| `/qualidade-dos-dados` | `data_quality` |
| `/sobre` | conteúdo estático + `MAX(gold_generated_at)` vindo das respostas |
| `/healthz` | endpoint `GET` sem chamada ao backend |

`[regiao]` é um slug do `admin1_name` (sem acento, minúsculo, com hífen). O mapa slug → nome vem da lista de regiões do país. Um slug desconhecido resulta em 404.

O ano é lido de `?ano=`. O validador `parseAno` usa o ano mais recente com dados quando o valor é inválido ou está fora da faixa de anos disponíveis.

Também ficam em `src/pages/` as páginas `404.astro` e `500.astro`.

### 5. Gráficos e mapas com Apache ECharts em `<script>` de componente
Os componentes são `EpiCurve.astro`, `ChoroplethMap.astro`, `AlertStrip.astro` e `RankingBars.astro`. Cada um renderiza no servidor:
- uma `<figure>`;
- a `<table>` com os mesmos dados, que é a alternativa sem JS e acessível;
- um `<script type="application/json">` com a série.

O `<script>` do componente importa `echarts/core` com tree-shaking (só os charts e componentes usados) e monta o gráfico sobre a figura, escondendo a tabela visualmente sem tirá-la dos leitores de tela. O Astro empacota e carrega esse script só nas páginas que usam o componente.

Os mapas registram o GeoJSON com `echarts.registerMap`, buscando `/geo/...`. O clique numa feição navega para a URL do país ou região preservando `?ano=`.

Alternativas descartadas:
- Chart.js + Leaflet: duas bibliotecas e dois estilos.
- Observable Plot com SVG gerado no servidor: interação limitada e exige jsdom no servidor.

Fica para depois o SSR em SVG do próprio ECharts, que permitiria gráfico visível sem JS.

### 6. Estilo
O site usa o **Atlas DS** em `frontend/design-system/` (ver o `README.md` e o `DATAVIZ.md` de lá), importado uma vez no `BaseLayout` (`design-system/css/atlas.css`) e sem cópia dos tokens em `src/`. Em resumo:
- CSS puro com tokens em custom properties;
- página clara com faixas escuras (cabeçalho, hero, rodapé) de texto claro;
- IBM Plex Sans e IBM Plex Mono;
- classes de coroplético `--viz-map-1..6` e níveis de alerta `--status-*` validados;
- tema escuro selecionado;
- `ds.js` para os comportamentos;
- `echarts-theme.js` com o `mountChart()` usado pelos componentes de gráfico (decisão 5).

Os componentes Astro (`KpiCard`, `EpiCurve` etc.) só aplicam as classes `.ds-*` e não definem estilo próprio, a não ser o layout específico da página. Tailwind foi descartado para manter zero dependências de estilo.

### 7. Cache HTTP
Um middleware (`src/middleware.ts`) adiciona `Cache-Control: public, max-age=${PAGE_CACHE_SECONDS}` às respostas HTML 200 e `no-store` às respostas 4xx e 5xx. Os assets `/_astro/*` recebem `max-age=31536000, immutable` do próprio servidor standalone. Os GeoJSON em `/geo/*` recebem `max-age=604800`, também via middleware. A suposição de que o standalone já envia `immutable` é verificada na tarefa 4.4; se ele não enviar, o middleware cobre esse caso.

### 8. Backend mock para desenvolvimento e testes
`frontend/mock-backend/` é um servidor Node mínimo, sem dependências, que serve `GET /gold/*` a partir de fixtures JSON e aplica os mesmos filtros e paginação. Ele também pode simular atraso e erro 503 por query flag. O `npm run dev:mock` sobe o mock e o `astro dev` apontando para ele. Assim o front pode ser desenvolvido antes de o backend novo existir.

### 9. Testes
- **Vitest**: `parseAno`, slugify de regiões, formatação numérica pt-BR, paginação e timeout de `gold.ts` (com `fetch` mockado).
- **Astro Container API**: renderização das páginas com fixtures, conferindo os KPIs no HTML, o 404 para país inexistente e o 503 com backend fora.
- **Playwright** (smoke), rodando contra `astro build && node dist/server/entry.mjs` + mock: viewport de 360 px sem overflow horizontal, página sem JS mostrando tabela, clique no mapa navegando, e a página `/sobre` sem requisição a chunks do ECharts.

### 10. Imagem e deploy
Dockerfile multi-stage `node:22-alpine`:
1. build: `npm ci` e `astro build`;
2. runtime: `npm ci --omit=dev`, `dist/`, usuário `node`, `HOST=0.0.0.0`, `PORT=4321`, `HEALTHCHECK` em `/healthz`, `CMD node ./dist/server/entry.mjs`.

Na `deploy/app.stack.yml`, o serviço `frontend` recebe `API_INTERNAL_URL=http://backend:8000` e a porta Traefik 4321. Ele fica nas redes `network_public` (entrada) e interna (backend).

## Risks / Trade-offs

- [Cada request de página dispara várias chamadas ao backend] → as chamadas de uma página rodam em paralelo (`Promise.all`); o Redis do backend absorve a repetição; há `max-age` curto nas páginas.
- [GeoJSON de municípios do Brasil pesado] → carregar só o arquivo da UF da página (`/geo/municipios/<UF>.json`) e conferir o tamanho na migração (meta de < 1 MB por arquivo, simplificar se passar).
- [Front novo do zero perde telas existentes (demografia, chat)] → listado como fora de escopo. A demografia do Brasil pode entrar depois na página do país.
- [Astro 7 é recente e a documentação de integrações pode divergir] → fixar versões exatas no `package-lock.json` e conferir `@astrojs/node` compatível na tarefa 1.2.
- [Dependência da mudança `decouple-architecture-bigquery` para o backend real] → o mock com fixtures desacopla o desenvolvimento. A integração real entra só no corte (grupo 6).

## Migration Plan

1. Desenvolver contra o mock até todas as páginas e testes passarem.
2. Publicar a imagem pelo CI e subir o serviço `frontend` na stack `atlas-app` em host temporário, junto do backend novo (ver `decouple-architecture-bigquery`, grupo 9).
3. Validar contra dados reais e então trocar o host para `dengue.contovisual.com.br`.
4. Rollback: voltar a stack antiga (imagem nginx `projeto_epidemiologia_frontend:1.0`).

## Open Questions

- Textos da página "Sobre" (créditos do PPGCC/UTFPR e citação dos dados).
