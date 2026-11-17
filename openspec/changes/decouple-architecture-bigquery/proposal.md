# Proposal

## Why

No `projeto_epidemiologia` tudo vive acoplado num só lugar: scripts de ingestão manuais, o projeto dbt, a API (que embute um job de cópia BigQuery → parquet a cada 1h) e o front, com imagens `anselmomendes/*:1.0` buildadas e publicadas à mão e a URL da API embutida no build do front. Não há CI, nem orquestração, nem versionamento de imagem, o que torna cada atualização de dados ou deploy um processo manual e frágil. O `atlas_epidemiologia` nasce para separar essas responsabilidades, com o BigQuery como datalake único e entrega contínua via GitHub Actions → DockerHub → Portainer na VPS.

## What Changes

- O `atlas_epidemiologia` passa a ser um monorepo com componentes independentes: `pipelines/` (ingestão), `airflow/` (orquestração e o projeto dbt em `airflow/dags/utfpr_dengue/`), `backend/`, `frontend/` e `deploy/` (stacks do Portainer).
- **BigQuery como datalake único**: camadas `raw` (ingestão), `bronze`/`silver`/`gold` (dbt). Nenhum componente guarda cópia local da gold como fonte de verdade.
- **Ingestão desacoplada**: os scripts de download/carga viram jobs idempotentes por fonte (um país/fonte por execução), executáveis manualmente por CLI e, depois, por tarefas do Airflow.
- **Modelagem desacoplada**: o projeto dbt (`utfpr_dengue`) fica em `airflow/dags/utfpr_dengue/`, com `profiles.yml` versionado lendo credenciais de variáveis de ambiente, rodável manualmente ou em container.
- **BREAKING (backend)**: a API deixa de sincronizar parquet e de ler via DuckDB; passa a consultar a gold diretamente no BigQuery, com **Redis** como cache de leitura. As rotas `/gold/*` e o contrato JSON atual são preservados.
- **CI (GitHub Actions)**: workflows filtrados por path que testam, buildam e publicam no DockerHub as imagens do backend, do frontend e (na fase final) do Airflow, com tags imutáveis (SHA do commit) além de `latest`.
- **CD (Portainer)**: stacks Swarm na VPS — stack da aplicação (frontend + backend + redis, atrás do Traefik) e, separada, stack de dados (Airflow). O GitHub Actions dispara o webhook do Portainer após publicar a imagem.
- **BREAKING (frontend)**: o front é refeito em Astro com SSR pela mudança `rebuild-frontend-astro`. A URL do backend deixa de ser fixada em build-time e passa a ser lida pelo servidor web em runtime.
- **Rotas novas no backend**: `/gold/casos-provaveis-brasil-semanal` e `/gold/casos-provaveis-uf-semanal`, usadas pelo site novo.
- **Orquestração (última fase)**: Airflow no Portainer dispara ingestão → `dbt build` → etapa do modelo de AI → invalidação do cache do backend. Até lá, essas etapas são executadas manualmente.

## Capabilities

### New Capabilities
- `data-ingestion`: carga das fontes epidemiológicas (SINAN, SIVIGILA, MINSA, SNVS, OBSALUD, PAHO, PLISA) na camada raw do BigQuery, por fonte, de forma idempotente e executável por CLI/container.
- `data-modeling`: transformação raw → bronze → silver → gold no BigQuery via dbt, com testes, configuração por ambiente e execução manual ou orquestrada.
- `gold-data-api`: API HTTP somente leitura que serve as tabelas gold a partir do BigQuery, com cache Redis, paginação, filtros e health check.
- `container-delivery`: build, teste e publicação versionada das imagens no DockerHub via GitHub Actions.
- `stack-deployment`: implantação das stacks (aplicação e dados) na VPS via Portainer, com configuração e segredos fora das imagens.
- `pipeline-orchestration`: DAGs do Airflow que encadeiam ingestão, modelagem dbt, modelo de AI e atualização do cache, com agendamento e reprocessamento.

### Modified Capabilities
<!-- Nenhuma: openspec/specs/ ainda não tem specs. -->

## Impact

- **Código migrado** do `projeto_epidemiologia`: `scripts/` → `pipelines/`, `utfpr_dengue/` → `airflow/dags/utfpr_dengue/`, `infra/api/` → `backend/`, `front/` → refeito em `frontend/` (Astro), `infra/docker-compose.yaml` → `deploy/`.
- **Backend**: remove `gold_sync.py`, a dependência de DuckDB e o volume `api_data`; adiciona `google-cloud-bigquery` + `redis`. Custo do BigQuery passa a depender do tráfego, mitigado pelo cache.
- **Frontend**: `src/lib/api.ts` e `Dockerfile`/`nginx.conf` mudam para configuração de runtime.
- **Infra**: novo serviço Redis na stack da aplicação; nova stack Airflow (webserver/scheduler + Postgres de metadados) na mesma VPS — exige avaliar memória disponível.
- **Segredos**: chave da service account GCP, token do DockerHub e URL de webhook do Portainer passam a ser GitHub Secrets / variáveis de stack; nenhum JSON de credencial no repositório.
- **Domínios**: mantém `dengue.contovisual.com.br` (front) e `api.dengue.contovisual.com.br` (API) no Traefik existente (`network_public`).
- **Fora de escopo**: o conteúdo do modelo de AI (só o ponto de execução no pipeline), novas telas no front, correções de modelos gold já listadas como limitações conhecidas, e a migração dos ramos DEM/Copernicus e SLayer.
