# Frontend: site do Atlas Epidemiológico da Dengue

O site público é feito em **Astro com SSR**, num servidor Node standalone. As páginas são renderizadas no servidor com os dados da API gold (`../backend/`), que é chamada pela URL interna. O navegador só fala com este servidor. JavaScript só é baixado onde há gráfico ou mapa, e sem ele cada página mostra os mesmos números em tabela.

## Hierarquia

| Rota | Conteúdo | Dados (API gold) |
|---|---|---|
| `/` | um cartão por seção: disponíveis com link e destaque, planejadas como "em breve" | Brasil semanal + UFs do ano mais recente |
| `/serie-historica` | casos prováveis por semana desde 2000, Brasil ou `?uf=SP`; indicadores e totais por ano | `/gold/casos-provaveis-brasil-semanal` ou `-uf-semanal?uf=` |
| `/mapa` | incidência por 100 mil por UF no ano (`?ano=2024`), ranking; clique abre a série da UF | `/gold/casos-provaveis-uf-semanal?epi_year=` |
| `/sobre` | fontes, definições e data da última geração dos dados | Brasil semanal (só a data) |
| `/healthz` | health check, sem chamar o backend | — |

As seções ficam num registro único, `src/data/secoes.ts`, lido pela página inicial e pelo cabeçalho. Para criar uma seção nova:
1. acrescente uma entrada no registro (`status: 'em-breve'` enquanto não houver página);
2. crie a página em `src/pages/`;
3. mude o status para `disponivel`.

O teste `tests/secoes.test.ts` confere que toda seção disponível tem página.

Valores inválidos nos filtros não geram erro. `?uf=XX` mostra o Brasil, `?ano=abc` mostra o ano mais recente, e a página avisa o que foi exibido. Se o backend falhar ou passar de `BACKEND_TIMEOUT_MS`:
- as páginas de seção respondem 503 com uma mensagem amigável;
- a página inicial e a Sobre continuam no ar, sem os números.

## Componentes

Todo elemento que aparece em mais de uma página, ou que encapsula um gráfico, é um componente em `src/components/`. As páginas só compõem esses componentes.

| Componente | Uso |
|---|---|
| `BaseLayout` (em `layouts/`) | `<head>`, CSS do design system, tema salvo, cabeçalho e rodapé |
| `SiteHeader`, `SiteFooter`, `PageHeader` | navegação pelas seções, rodapé e trilha "Início › Seção" |
| `SectionCard` | cartão da página inicial |
| `KpiStrip`, `KpiCard` | faixa de indicadores (o primeiro no bloco azul) e variação com seta |
| `FilterForm` | filtros por formulário GET (UF, ano): funciona sem JS e, com JS, envia ao mudar |
| `TimeSeriesChart` | série semanal (ECharts), com zoom e tabela alternativa |
| `ChoroplethMap`, `RankingBars` | mapa das UFs em 6 faixas fixas e ranking em barras |
| `DataTable`, `EmptyState`, `BackendError`, `SourceNote`, `Icon` | tabela, "sem dados", indisponibilidade, fonte e data, ícone |

A lógica fica fora dos componentes:
- `src/lib/server/gold.ts` faz a paginação, o timeout e trata o `BackendUnavailableError`. Só pode ser importado no servidor: o ESLint bloqueia o import em `<script>`.
- `src/lib/series.ts` tem as agregações.
- `src/lib/filtros.ts` lê os filtros da URL.
- `src/lib/format.ts` faz a formatação pt-BR.
- `src/lib/classes.ts` define as faixas do mapa.

## Design system

O visual segue o design system "Painel". A referência fica em `design-system/status_invest/`, **só local** (ignorada pelo Git e pela imagem) e serve apenas para consulta. O site usa uma **cópia versionada** só do que precisa:
- `src/styles/ds/`: tokens e CSS, com `index.css` de entrada e fontes Source pelo `@fontsource`;
- `src/scripts/ds/`: `ds.js` e `echarts-theme.js`;
- `public/icons.svg`.

Os componentes só aplicam classes `.ds-*`. Para atualizar a cópia, altere a referência e rode, na raiz do repositório:

```sh
python -I frontend/scripts/copiar-design-system.py frontend
```

O script troca os cabeçalhos e falha se sobrar alguma menção à página de referência.

## Variáveis (runtime)

| Variável | Padrão | Uso |
|---|---|---|
| `API_INTERNAL_URL` | — (obrigatória) | URL interna da API gold, ex.: `http://backend:8000` |
| `BACKEND_TIMEOUT_MS` | 8000 | tempo máximo por chamada ao backend |
| `PAGE_CACHE_SECONDS` | 300 | `Cache-Control: max-age` das páginas 200 (erros saem com `no-store`) |
| `PUBLIC_SITE_URL` | — | URL pública (canonical e Open Graph) |
| `HOST`, `PORT` | `0.0.0.0`, `4321` (na imagem) | servidor Node |

O `npm start` (`scripts/start.mjs`) recusa subir sem uma `API_INTERNAL_URL` válida. A URL nunca vai para o HTML nem para o JavaScript do navegador. Os assets com hash (`/_astro/`, inclusive o GeoJSON das UFs) saem com cache imutável.

## Desenvolvimento

Node 22+. A partir de `frontend/`:

```sh
npm ci
cp .env.example .env     # API_INTERNAL_URL=http://localhost:8000 (API da stack platform/)
npm run dev              # http://localhost:4321, contra a API real
npm run dev:mock         # sem backend: sobe o backend mock (mock-backend/) e aponta o site para ele
```

A API real sobe com a stack local da plataforma (`./platform/dev.ps1 up`, serviços `backend` e `redis`). A mesma stack também sobe este site já em imagem de produção, o serviço `frontend` em `http://127.0.0.1:4321`.

O backend mock (`mock-backend/`, sem dependências) serve as mesmas rotas, com filtros e paginação, a partir de fixtures determinísticas:
- UFs SP, MG, RJ e AC;
- anos 2024, 2025 e 2026 até a SE 20.

Ele simula atraso (`?__atraso=ms`) e falha (`?__falha=1` ou `POST /__mock/estado {"falhar": true}`).

## Testes

```sh
npm run lint        # ESLint (inclui o bloqueio de src/lib/server em scripts de cliente)
npm run check       # astro check (tipos)
npm test            # Vitest: lib, mock, componentes e páginas (Container API contra o mock)
npm run build && npm run test:e2e   # Playwright: build de produção + mock (npx playwright install chromium)
```

O smoke de ponta a ponta confere:
- 360 px sem rolagem horizontal;
- a série sem JavaScript;
- o tooltip;
- o clique numa UF do mapa;
- que `/sobre` não baixa JS de gráfico;
- a navegação pela trilha.

No CI, os jobs `frontend` e `images` do `.github/workflows/ci.yml` rodam essas mesmas etapas.

## Imagem

```sh
docker build -t atlas-epidemiologia-frontend:local frontend
# rede com inspeção TLS: --secret id=extra_ca,src=platform/certs/ca-bundle.pem
docker run --rm -p 4321:4321 -e API_INTERNAL_URL=http://host.docker.internal:8000 atlas-epidemiologia-frontend:local
```

É multi-stage `node:22-alpine`, roda como o usuário `node`, tem `HEALTHCHECK` em `/healthz` e não leva credenciais. A publicação no DockerHub e o deploy pelo Portainer ainda estão pendentes (mudança `rebuild-frontend-astro`, tarefas 8.2 e 8.3).
