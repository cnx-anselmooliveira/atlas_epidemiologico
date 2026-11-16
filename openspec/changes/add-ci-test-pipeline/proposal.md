# Proposal

## Why

O fluxo do projeto é dev → hml → main, e cada promoção dispara imagens e deploys. Hoje nada verifica automaticamente o código que chega a `hml` e `main`. Os testes (23 do pacote `ml`, integridade das DAGs, builds das imagens, ponta a ponta da plataforma) só rodam quando alguém se lembra de rodá-los no notebook. O repositório agora é público e as DAGs de hml e prod vão ser lidas direto das branches `hml` e `main`. Um código quebrado nessas branches chega ao Airflow imediatamente, então essas branches precisam de um portão de testes obrigatório.

## What Changes

- **Workflow `ci.yml` no GitHub Actions**, disparado em:
  - push em `hml` e `main`;
  - pull requests com destino `hml` ou `main`;
  - execução manual.
- **Jobs paralelos, cobrindo todos os testes do projeto:**
  - **lint:** `ruff` (lint + formato) no pacote `ml` e nas DAGs, `shellcheck` nos scripts, `actionlint` nos workflows e `docker compose config` nos composes;
  - **ml-tests:** `pytest` do pacote `ml`, sem rede e sem credenciais;
  - **ml-models-tests:** `pytest -m models` com o grupo de dependências `models`, a parte pesada (CatBoost, PyTorch, PyMC, Chronos);
  - **images:** build das imagens `ml` (runtime e notebook), `mlflow` e `airflow`, sem publicar;
  - **dags:** teste de integridade das DAGs dentro da imagem do Airflow construída no job anterior;
  - **platform-e2e:** sobe o compose de dev no runner (Postgres + MLflow + Airflow, artefatos em volume local, sem segredos), dispara a DAG de exemplo e confere a run no MLflow;
  - **frontend:** `npm ci` + `astro build`;
  - **openspec:** valida todas as mudanças em modo estrito;
  - **ci-ok:** agrega os resultados num único check, que fica obrigatório na proteção das branches `hml` e `main`.
- **Workflow reutilizável (`workflow_call`)**: a publicação de imagens da `add-ml-platform` (módulo 6) só publica depois de o `ci.yml` passar.
- **Proteção das branches `hml` e `main`**: o check `ci-ok` passa a ser obrigatório antes do merge.

## Capabilities

### New Capabilities
- `ci-test-pipeline`: quais verificações rodam, quando rodam, o que bloqueia um merge em `hml` e `main` e como os resultados ficam visíveis.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/. Interage com release-promotion (add-ml-platform, ainda não arquivada): a publicação de imagens passa a depender deste pipeline. -->

## Impact

- **Arquivos novos:**
  - `.github/workflows/ci.yml`;
  - `.github/actionlint.yaml`, se necessário;
  - `platform/ci/e2e.sh`, o teste de ponta a ponta reaproveitável localmente;
  - o marcador `models` registrado no `ml/pyproject.toml`.
- **GitHub:**
  - regras de proteção nas branches `hml` e `main`, que exigem `ci-ok` e pull request;
  - o repositório é público, então o Actions roda sem custo nos runners `ubuntu-latest`.
- **Tempo de CI:** estimado em 15–25 min por execução. O job mais longo é o `platform-e2e`, e o `ml-models-tests` instala torch CPU. Há cache de `uv`, npm e camadas Docker.
- **Outras mudanças:**
  - `add-ml-platform`: os workflows de publicação (tarefas 6.1–6.2) passam a chamar este pipeline, em vez de repetir lint e testes. Isso fica registrado numa tarefa de alinhamento.
  - `add-dengue-forecast-models`: os testes marcados `models` passam a rodar no CI assim que existirem.
- **Fora de escopo:**
  - publicar imagens e fazer deploy (`add-ml-platform`);
  - testes contra o BigQuery real ou o bucket GCS, que exigiriam segredos no CI;
  - cobertura mínima obrigatória;
  - CI na branch `dev` (o feedback de dev vem dos testes locais e dos PRs para `hml`).
