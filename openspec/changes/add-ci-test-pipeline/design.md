# Design

## Context

- **Repositório:** `cnx-anselmooliveira/atlas_epidemiologico`, **público**. Tem as branches `dev`, `hml` e `main` e ainda nenhum workflow (`.github/` não existe).
- **O que existe para testar:**
  - `ml/`: uv, Python 3.12, 23 testes pytest sem rede, `ruff` configurado. Os testes de previsão estão chegando pela `add-dengue-forecast-models`, que prevê o marcador `models` para os testes pesados.
  - `airflow/tests/test_dags.py`: roda dentro da imagem do Airflow, sem banco.
  - Dockerfiles: `ml/` (estágios `runtime` e `notebook`), `infra/mlflow/` e `airflow/` (contexto = raiz).
  - Scripts shell: `infra/mlflow/entrypoint.sh`, `airflow/config/init.sh`, `platform/postgres/init-databases.sh`.
  - Composes: `platform/compose.dev.yml` e `compose.ca.yml`.
  - `frontend/`: Astro, template inicial, Node ≥ 22. Os design systems ficam fora do git.
  - OpenSpec: 5 mudanças em `openspec/changes/`, validáveis com `npx @fission-ai/openspec@2.0.0`.
- **Teste manual já feito:** o ponta a ponta local (compose up → DAG → MLflow) funcionou. O script vai automatizar exatamente esses passos.

## Goals / Non-Goals

**Goals:**
- Um workflow, um check obrigatório (`ci-ok`) e jobs paralelos com cache, de modo que o tempo total seja o do job mais lento.
- O teste de ponta a ponta reaproveitável fora do CI, como um script único.

**Non-Goals:**
- Matriz de versões de Python e Node: o projeto fixa 3.12 e 22.
- Testes de carga.
- Relatório de cobertura.

## Decisions

### 1. Um workflow `ci.yml` com jobs paralelos
```yaml
on:
  push:          { branches: [hml, main] }
  pull_request:  { branches: [hml, main] }
  workflow_dispatch:
  workflow_call:                 # usado pela publicação de imagens (add-ml-platform)
concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }
permissions: { contents: read }
```

| Job | Runner e passos | Tempo esperado |
|---|---|---|
| `lint` | `astral-sh/setup-uv` → `ruff check` + `ruff format --check` em `ml/` e `airflow/dags/` (config do `ml/pyproject.toml`); `shellcheck` nos `*.sh`; `actionlint` (binário oficial); `docker compose -f platform/compose.dev.yml config -q` com `.env` fictício | ~1 min |
| `ml-tests` | `uv sync --frozen` → `pytest -m "not models"` | ~1 min |
| `ml-models-tests` | `uv sync --frozen --extra models` (torch do índice CPU) → `pytest -m models`. O código de saída 5 ("nenhum teste coletado") é aceito enquanto os testes de modelo não existem | ~4–6 min |
| `images` | `docker/setup-buildx-action` + `docker/build-push-action` com `push: false` para `ml` (runtime e notebook), `mlflow` e `airflow`, com `cache-to/from: type=gha,scope=<imagem>` e `ATLAS_GIT_SHA=${{ github.sha }}` | ~6–10 min frio, ~2 min com cache |
| `dags` | `needs: images`; rebuild do Airflow (cache quente) com `load: true` → `python /opt/atlas/tests/test_dags.py` | ~1–2 min |
| `platform-e2e` | `needs: images`; `platform/ci/e2e.sh` (abaixo) | ~6–8 min |
| `frontend` | `actions/setup-node` (22, cache npm) → `npm ci` → `npm run build` em `frontend/` | ~1 min |
| `openspec` | `npx --yes @fission-ai/openspec@2.0.0 validate --all --strict` | <1 min |
| `ci-ok` | `needs: [todos]`, `if: always()`; falha se algum resultado não for `success` | segundos |

Alternativas rejeitadas:
- **Um workflow por pasta, filtrado por `paths`:** obrigaria vários checks obrigatórios, e um check não disparado bloqueia o merge.
- **Passar imagens entre jobs como artefato (`docker save`):** 2–4 GB por execução. O cache GHA do BuildKit resolve com menos tráfego.

### 2. Teste de ponta a ponta: `platform/ci/e2e.sh`
É um script bash idempotente que roda no runner, no Git Bash ou no WSL:
1. **`.env`:** gera um `.env` temporário com senhas aleatórias, `MLFLOW_ARTIFACTS_BUCKET` vazio (volume local) e `ATLAS_GIT_SHA` do commit.
2. **Subida:** `docker compose -p atlas-ci -f platform/compose.dev.yml up -d --build` (com cache GHA, via `COMPOSE_BAKE=true` e `--build-arg BUILDKIT_INLINE_CACHE=1`, ou build prévio no job).
3. **Espera:** aguarda os 6 serviços `healthy`, com limite de 10 min.
4. **Disparo:** pega um token em `/auth/token`, despausa e dispara `atlas_ml_example_training`, e espera um estado final, com limite de 10 min.
5. **Asserções:**
   - estado `success`;
   - run em `atlas/example` com `atlas.env=dev` e `atlas.git_sha` igual ao commit;
   - alias `@dev` em `atlas-example`.
6. **Em falha:** `docker compose logs` vai para `e2e-logs/`. O workflow publica esse diretório como artefato (`actions/upload-artifact`, retenção de 7 dias).
7. **Sempre:** `docker compose down -v` ao final, num `trap`.

As portas continuam em `127.0.0.1`, e o runner as acessa localmente.

### 3. Marcador `models`
O `ml/pyproject.toml` registra `markers = ["models: testes que exigem o grupo de dependências models"]`. Os testes leves rodam com `-m "not models"` e os pesados com `-m models`. A `add-dengue-forecast-models` marca os testes dela com esse nome, como previsto no design dela.

### 4. Proteção das branches
Configurada por `gh api` (tarefa) e registrada no `platform/README.md`. Para `hml` e `main`:
- `required_status_checks.contexts = ["ci-ok"]`, com `strict: true` (a branch precisa estar atualizada);
- `required_pull_request_reviews` com 0 aprovações, para exigir PR sem exigir revisor (o projeto tem um único mantenedor);
- `enforce_admins: true`, para que o push direto seja rejeitado também para o dono;
- `allow_force_pushes: false`.

O check `promotion-guard` da `add-ml-platform` será acrescentado à mesma regra quando existir.

### 5. Integração com a publicação de imagens (`add-ml-platform`, módulo 6)
Os workflows de publicação passam a ter um primeiro job `tests: uses: ./.github/workflows/ci.yml`, e o build e push só rodam com `needs: tests`. Com isso, deixam de repetir ruff, pytest e `DagBag`. O alinhamento do texto das tarefas 6.1 e 6.2 de lá é uma tarefa desta mudança.

### 6. Versões fixadas
As actions são fixadas por versão maior: `actions/checkout@v4`, `astral-sh/setup-uv@v6`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`, `actions/setup-node@v4` e `actions/upload-artifact@v4`. O `actionlint` e o OpenSpec ficam em versões exatas. O Dependabot de actions fica para depois.

## Risks / Trade-offs

- **[`platform-e2e` instável: tempo de subida do Airflow em runner compartilhado]** → limites generosos, espera por health check em vez de `sleep` fixo e logs anexados em falha. Se ficar instável, ele pode sair do `ci-ok` sem mudar os demais.
- **[`ml-models-tests` lento por causa do torch]** → índice CPU, cache do uv e só em `hml`/`main`/PRs.
- **[Proteção com `enforce_admins` trava correções urgentes em `main`]** → o caminho de correção continua sendo PR `hml → main`, rápido com o CI verde. Uma emergência exige desligar a regra conscientemente pelo GitHub.
- **[Disco do runner (cerca de 14 GB livres) com várias imagens grandes]** → limpar com `docker builder prune` entre builds no job `images`, se necessário, e usar `load: true` só onde a imagem é executada.

## Migration Plan

1. Criar o workflow em `dev`, abrir PR `dev → hml` e ajustar até ficar verde.
2. Configurar a proteção de `hml` e `main` só depois do primeiro verde, para não travar o próprio PR que introduz o CI.
3. **Rollback:** remover a regra de proteção e reverter o workflow. Nenhum dado é afetado.

## Open Questions

- Os testes de modelo (`ml-models-tests`) devem ser obrigatórios no `ci-ok` desde já ou só depois de a `add-dengue-forecast-models` entregar os modelos? Proposta: obrigatórios desde já, já que o código de saída 5 é tolerado enquanto não há testes.
