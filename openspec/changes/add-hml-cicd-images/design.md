# Design

## Context

Observado no repositório:

- `_image.yml` publica uma imagem (testa via `ci.yml`, tag pela origem, versão imutável, webhook do Portainer em hml e em versão). Só `frontend.yml` e `backend.yml` o chamam. O próprio cabeçalho do `_image.yml` promete `ml/airflow/mlflow` "na add-ml-platform", que nunca foi feito.
- O `ci.yml` já constrói (sem publicar) seis imagens: `ml`, `ml-notebook`, `mlflow`, `airflow`, `backend`, `frontend`.
- A imagem do Airflow **embute** as DAGs (`COPY airflow/dags`), o projeto dbt e o `atlas_ml` (`COPY ml/src`). Em dev as DAGs são montadas por volume; em hml e prod só a imagem existe.
- `deploy/` tem só `app.stack.yml`. O backend lá recebe a service account por `GOOGLE_APPLICATION_CREDENTIALS_JSON`, mas não recebe o bucket e o prefixo das figuras (`forecast_bucket` e `forecast_prefix` têm padrão no código). As tags caem em `latest`, que nenhum workflow publica.
- Os workflows de imagem filtram por `paths`: um push em `hml` que não toque os arquivos de uma imagem não a publica, então a primeira tag `hml` de uma imagem depende de um commit artificial.
- O mesmo `PORTAINER_WEBHOOK_*` é usado quando a tag não é `dev`, isto é, em hml **e** em versão.
- O repositório é público e não tinha nenhum secret quando se tentou publicar.

## Goals / Non-Goals

**Goals:**
- Todas as imagens que o Portainer usa existem no DockerHub com tag `hml` e `X.Y`.
- Falha rápida e legível quando falta secret.
- hml e prod não se misturam no deploy.
- Um passo a passo que dispensa tentativa e erro.

**Non-Goals:**
- Migrar para Kubernetes, GitOps ou outro orquestrador; o destino continua sendo o Portainer em Swarm.
- Publicar `ml-notebook`, `postgres` ou `redis`.
- Assinar imagens (cosign) ou gerar SBOM; fica como evolução.
- Criar a VPS, o DNS ou os certificados.

## Decisions

1. **Um workflow fino por imagem, sobre o `_image.yml`.** `airflow.yml`, `mlflow.yml` e `ml.yml` repetem o padrão de `frontend.yml`. Alternativa descartada: uma matriz única num só arquivo, porque perderia o filtro por caminho e a concorrência por imagem. O `airflow` usa contexto `.` e `file: airflow/Dockerfile`; o `ml` usa `context: ml` e o alvo `runtime` (entrada nova `target` no `_image.yml`). O `ml` é publicado para treino avulso em container e reprodutibilidade, embora o stack da VPS use o `atlas_ml` embutido no Airflow.

2. **Caminhos que refletem dependências reais.** `airflow`: `airflow/**`, `ml/**` e `.github/workflows/{airflow,_image}.yml`. `ml`: `ml/**`. `mlflow`: `infra/mlflow/**`. Mais `workflow_dispatch` em todos, para a primeira publicação e para republicar à mão.

3. **Job `secrets-check` antes de tudo no `_image.yml`.** Recebe os secrets, confere se cada um está preenchido e imprime só os nomes que faltam e o caminho de criação. Os demais jobs dependem dele, então a falha acontece em segundos e antes do `ci.yml` completo. O valor nunca é impresso.

4. **GitHub Environments `hml` e `prod` para os webhooks.** `DOCKERHUB_*` ficam como secrets do repositório (iguais em todos os ambientes). `PORTAINER_WEBHOOK_<IMAGEM>` ficam em cada Environment, com o mesmo nome. O job de publicação escolhe o `environment` pela origem (`hml` → `hml`; tag → `prod`; `dev` → nenhum). O Environment `prod` pode exigir aprovador. Alternativa descartada: nomes distintos (`..._HML`, `..._PROD`) como secrets do repositório, porque nada impediria um uso trocado e não há aprovação por ambiente.

5. **Sem `latest`.** O CI não a publica e o stack não deve usá-la. `FRONTEND_TAG`, `BACKEND_TAG` e as demais viram variáveis obrigatórias. O webhook do Portainer recebe `?tag=` e atualiza o serviço para essa tag.

6. **Stack `platform` versionado, só com referências.** Postgres, MLflow e Airflow (api-server, scheduler, dag-processor, triggerer) com `${VAR}` e Docker secrets, espelhando o `compose.dev.yml` sem volumes de código nem portas no host. A chave da service account vai como **Docker secret** (`/run/secrets/...`), apontada por `GOOGLE_APPLICATION_CREDENTIALS` e `DBT_BQ_KEYFILE`; a Connection do Airflow guarda só o caminho. Alternativa descartada: variável de ambiente com o JSON, porque aparece no `docker inspect`. No stack `app` isso já existe (`GOOGLE_APPLICATION_CREDENTIALS_JSON`); migrar para Docker secret fica como evolução.

7. **Conta de leitura própria para o backend.** O backend lê BigQuery (datasets `gold` e `forecast`) e o prefixo `forecast/` do bucket com uma service account só de leitura (BigQuery Data Viewer nos datasets, Job User no projeto, Storage Object Viewer limitado ao prefixo por condição IAM). Nunca a conta de treino. `FORECAST_BUCKET` e `FORECAST_PREFIX` entram no stack.

8. **Barreira no `check-secrets.sh` para o stack e `deploy/`.** No `docker-compose.yml` da raiz (o stack fica fora de `deploy/`, ver `add-hml-stack`) e em `deploy/*.yml`, chaves cujo nome contém `PASSWORD`, `TOKEN`, `SECRET`, `KEY` ou `WEBHOOK` só podem receber `${...}`, `/run/secrets/...` ou ficar vazias. Cobre o caso de alguém digitar um valor "só para testar".

9. **Roteiro de promoção.** `dev` → `hml` (merge) publica `hml` e chama o webhook do Environment `hml`; `main` + tag `vX.Y` publica `X.Y` e, após aprovação, chama `prod`. A proteção de branch (`ci-ok` obrigatório em `hml` e `main`) é configurada pelo usuário no GitHub e documentada.

## Risks / Trade-offs

- **Imagem do Airflow grande e lenta** (venvs do ML e do dbt): o build em CI pode passar de 15 min. Mitigação: cache `gha` por escopo, já existente, e filtro por caminho.
- **Dois Environments com os mesmos nomes de secret** confundem na primeira configuração. Mitigação: o passo a passo traz uma tabela por Environment e o `secrets-check` informa o que faltou.
- **Aprovação em `prod` bloqueia o deploy** se ninguém estiver disponível. É o comportamento desejado; pode ser desligado no Environment.
- **Docker secret no Swarm é imutável**: trocar a chave exige criar um secret novo e atualizar o stack. Fica documentado na rotação.
- **O stack `platform` não foi exercitado numa VPS** nesta mudança; a validação local é `docker stack config` e o teste de ponta a ponta do CI. O primeiro `up` real é do usuário e pode revelar ajustes.
- **Imagens públicas no DockerHub** não têm segredo, mas revelam a estrutura do projeto. O repositório já é público, então não há impacto novo.
