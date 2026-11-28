# Deploy: stack, imagens e credenciais

**Regra:** nenhuma senha, token ou arquivo de credencial do Google vai para o Git (nem em branch `dev`, `hml` ou `main`), para o compose versionado ou para uma imagem. O repositório é público. O stack (`docker-compose.yml`, na raiz) só tem **referências** a variáveis (`${NOME}`); o valor é digitado na interface de quem executa.

## Visão geral

- **Um stack para os dois ambientes:** o `docker-compose.yml` da raiz sobe Postgres, MLflow, Airflow (init, api-server, scheduler, dag-processor, triggerer), API, site e Redis, em formato Swarm. `atlas-hml` lê a branch `hml`; `atlas-prod` lê a `main`. A diferença está só nas variáveis.
- **Variáveis:** todas estão listadas e comentadas no `.env.example` da raiz (grupo "Stack de hml e prod"). No Portainer, use "Load variables from .env file" com esse arquivo e preencha os valores.
- **Sem portas no host:** o site, a API, o Airflow e o MLflow saem pelo Traefik; Postgres e Redis só na rede interna.

| Credencial | Onde fica | Quem usa |
|---|---|---|
| Chave da service account de **leitura** (BigQuery `gold` e `forecast`, prefixo `forecast/` do bucket) | **Docker secret** `atlas_<ambiente>_backend_sa` | `backend` |
| Chave da service account de treino e do dbt | **Docker secret** `atlas_<ambiente>_training_sa` | Airflow (tarefas, dbt via Cosmos) |
| Chave da service account do MLflow (só o bucket) | **Docker secret** `atlas_<ambiente>_mlflow_sa` | MLflow |
| **Hash** da senha do Jupyter (nunca a senha em texto; o Jupyter não recebe nenhuma outra credencial) | variável do stack `JUPYTER_PASSWORD_HASH` | `jupyter` |
| Senhas do Postgres (`POSTGRES_PASSWORD`, `MLFLOW_DB_PASSWORD`, `AIRFLOW_DB_PASSWORD`) | variáveis do stack no Portainer | Postgres, MLflow, Airflow |
| `AIRFLOW_ADMIN_PASSWORD`, `AIRFLOW_JWT_SECRET`, `AIRFLOW_FERNET_KEY` | variáveis do stack | Airflow |
| `MLFLOW_ADMIN_USERNAME`, `MLFLOW_ADMIN_PASSWORD`, `MLFLOW_FLASK_SECRET_KEY` | variáveis do stack | MLflow e tarefas de treino |
| Hosts, tag, bucket, limites (`FRONTEND_HOST`, `IMAGE_TAG`, `ATLAS_BUCKET`…) | variáveis do stack (não são segredo) | `docker-compose.yml` |
| Acesso do Airflow ao GCP (GCS dos docs, cache do Cosmos) | Connection `google_cloud_default`, já montada pelo stack com o caminho do secret | tarefas do Airflow |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | **secrets do repositório** no GitHub | workflows de imagem |
| `PORTAINER_WEBHOOK_STACK` | **secret de cada Environment** (`hml` e `prod`) do GitHub | job de deploy |

## Imagens publicadas no DockerHub

Todas saem de `anselmomendes/atlas-epidemiologia-<imagem>`; os repositórios são criados no primeiro push.

| Imagem | Workflow | Muda com | Usada por |
|---|---|---|---|
| `frontend` | `frontend.yml` | `frontend/**` | site |
| `backend` | `backend.yml` | `backend/**` | API gold |
| `airflow` | `airflow.yml` | `airflow/**` e `ml/**` (embute as DAGs, o dbt e o `atlas_ml`) | Airflow (4 serviços) |
| `mlflow` | `mlflow.yml` | `infra/mlflow/**` | servidor MLflow |
| `ml` (alvo `runtime`) | `ml.yml` | `ml/**` | treino avulso em container |
| `ml-notebook` (alvo `notebook`) | `ml.yml` | `ml/**` | Jupyter de exploração (mesmas versões do Airflow) |

Não são publicadas: `postgres` e `redis` (imagens oficiais). A `ml-notebook` deixou de ser só de desenvolvimento: é a imagem do Jupyter do stack de hml.

**Tags:** push em `dev` → `dev`; push em `hml` → `hml`; tag `vX.Y` em `main` → `X.Y` (imutável: falha se a versão já existe). Nunca há `latest`: o stack recebe a tag em `IMAGE_TAG` e recusa subir sem ela. Para publicar a primeira tag `hml` de uma imagem sem mexer em arquivo dela, abra Actions › workflow da imagem › **Run workflow** na branch `hml`.

A imagem do Airflow tem mais de 10 GB em camadas (venvs do ML e do dbt); o primeiro push e o primeiro pull na VPS demoram.

## Pré-requisitos da VPS

Confira cada item **antes** do primeiro deploy. Os comandos rodam na VPS (no gerenciador do Swarm), salvo onde indicado.

| Item | Como conferir | Esperado |
|---|---|---|
| Docker Engine | `docker version --format '{{.Server.Version}}'` | 20.10 ou superior (o `airflow-init` usa `mode: replicated-job`); testado com 29.3.1 |
| Swarm ativo, nó gerenciador | `docker info --format '{{.Swarm.LocalNodeState}} {{.Swarm.ControlAvailable}}'` | `active true` |
| Portainer | versão no rodapé; o ambiente deve ser o Swarm | testado com a 2.45.3 (CE) |
| Rede pública | `docker network inspect network_public --format '{{.Driver}} {{.Scope}}'` | `overlay swarm`, a mesma rede do Traefik |
| Traefik | `docker service inspect traefik --format '{{json .Spec.TaskTemplate.ContainerSpec.Args}}'` | com `entrypoints.websecure` e `certificatesresolvers.letsencryptresolver`; versão que tenha o middleware `ipallowlist` (2.10 ou 3) |
| Docker secrets | `docker secret ls --filter name=atlas_hml_` | `atlas_hml_backend_sa`, `atlas_hml_training_sa`, `atlas_hml_mlflow_sa` |
| Nó e disco | `docker node ls` e `df -h /var/lib/docker` | um nó com o papel de `PLACEMENT_ROLE` e pelo menos 30 GB livres (a imagem do Airflow passa de 10 GB) |
| DNS | `dig +short <host>` para `FRONTEND_HOST`, `API_HOST`, `AIRFLOW_HOST` e `MLFLOW_HOST` | o IP da VPS |
| Imagens `hml` | `docker manifest inspect anselmomendes/atlas-epidemiologia-<imagem>:hml` para `frontend`, `backend`, `airflow` e `mlflow` | sai com código 0 |
| Stack na branch `hml` | `curl -fsS https://raw.githubusercontent.com/cnx-anselmooliveira/atlas_epidemiologico/hml/docker-compose.yml \| head -1` | a primeira linha do arquivo (se der 404, o PR `dev` → `hml` ainda não foi mergeado) |
| Webhook | secret `PORTAINER_WEBHOOK_STACK` no Environment `hml` | existe (sem ele, o deploy só avisa "não acionado") |

## Passo a passo: criar o stack de hml

### 1. DockerHub e GitHub

1. Use uma conta com escrita no namespace `anselmomendes`. Em Account settings › Personal access tokens, gere um token **Read & Write** (`atlas-github-ci`) e copie-o na hora: ele só aparece uma vez.
2. No GitHub, em Settings › Secrets and variables › Actions, crie os secrets do repositório `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN`. Sem eles, o primeiro job de cada workflow de imagem (`secrets-check`) falha em segundos listando o que falta.
3. Em Settings › Environments, crie `hml` e `prod`. Em `prod`, ative **Required reviewers**: o deploy de versão espera aprovação.

### 2. Service accounts

O backend lê o BigQuery (datasets `gold` e `forecast`) e o prefixo `forecast/` do bucket de figuras. Use uma conta **só de leitura**, nunca a de treino:

```bash
P=ppgcc-dengue-project
gcloud iam service-accounts create atlas-backend-ro --project "$P" --display-name "Atlas backend (leitura)"
SA="atlas-backend-ro@${P}.iam.gserviceaccount.com"
# executar consultas no projeto
gcloud projects add-iam-policy-binding "$P" --member "serviceAccount:${SA}" --role roles/bigquery.jobUser
# leitura nos dois datasets: console BigQuery › dataset gold (e forecast) › Compartilhar › adicionar
#   o principal ${SA} com o papel "Leitor de dados do BigQuery" (roles/bigquery.dataViewer)
# figuras: só o prefixo forecast/ do bucket
gcloud storage buckets add-iam-policy-binding gs://ppgcc-bucket \
  --member "serviceAccount:${SA}" --role roles/storage.objectViewer \
  --condition 'expression=resource.name.startsWith("projects/_/buckets/ppgcc-bucket/objects/forecast/"),title=forecast-figuras'
```

A condição de IAM exige acesso uniforme no nível do bucket. As contas de treino (leitura e escrita no BigQuery) e do MLflow (só o bucket) são as mesmas do desenvolvimento ou contas próprias do ambiente. Gere cada chave fora do repositório e **apague o arquivo local** depois de colá-la no Portainer.

### 3. Docker secrets no Portainer

Em Secrets › Add secret, crie os do ambiente, colando o JSON de cada chave:

| Nome | Conteúdo |
|---|---|
| `atlas_hml_backend_sa` | chave da conta de leitura do backend |
| `atlas_hml_training_sa` | chave da conta de treino e dbt |
| `atlas_hml_mlflow_sa` | chave da conta do MLflow |

O nome leva o ambiente porque os secrets são do cluster inteiro; em produção, `atlas_prod_...`. **Rotação:** um Docker secret não pode ser alterado. Remova o stack, apague o secret, crie-o de novo com o mesmo nome e crie o stack outra vez; os volumes (banco, logs) são mantidos.

### 4. O stack no Portainer, pelo GitHub

1. Stacks › Add stack › **Repository**. Nome `atlas-hml`.
2. Repository URL `https://github.com/cnx-anselmooliveira/atlas_epidemiologico`, **Repository reference** `refs/heads/hml`, **Compose path** `docker-compose.yml` (o mesmo nome do CI e das verificações). O repositório é público: não há credencial de acesso. Se um dia ele ficar privado, guarde um token de leitura em **Authentication** no próprio Portainer, nunca no Git.
3. **Environment variables › Load variables from .env file** com o `.env.example`; depois preencha: `ATLAS_ENV=hml`, `IMAGE_TAG=hml`, os hosts (`FRONTEND_HOST`, `FRONTEND_PUBLIC_URL`, `API_HOST`, `AIRFLOW_HOST`, `MLFLOW_HOST`), `ADMIN_ALLOWED_CIDRS` e todas as senhas (troque cada `troque-esta-senha`; a Fernet key vem de `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; senhas distintas para Postgres, MLflow e Airflow).
4. **GitOps updates:** desligue a sincronização por intervalo (ela poderia implantar antes de a imagem existir) e ative o **webhook do stack**, com a opção de baixar as imagens de novo (*re-pull image*). Copie a URL do webhook.
5. No GitHub, em Settings › Environments › `hml`, crie o secret `PORTAINER_WEBHOOK_STACK` com essa URL. O de `prod` é outro, do stack `atlas-prod`.

Depois de cada imagem publicada em `hml`, o CI chama o webhook e o Portainer refaz o deploy. Se o secret não existir, a imagem é publicada e o job avisa "deploy não acionado" sem falhar. Mudando só o `docker-compose.yml` em `hml` (sem imagem nova), faça o redeploy à mão no Portainer.

### 5. Primeiro boot

1. O Postgres cria os bancos `airflow`, `mlflow` e `mlflow_auth` e os usuários `airflow` e `mlflow` (cada um só conecta nos próprios bancos). Isso só acontece com o volume vazio; para trocar uma senha depois, use `ALTER ROLE ... PASSWORD ...` no Postgres e atualize a variável.
2. O serviço `airflow-init` roda uma vez (migra o banco e cria o admin) e aparece como concluído; o scheduler, o dag-processor, o triggerer e o api-server esperam a migração e ficam saudáveis sozinhos. A cada novo deploy o init roda de novo, sem efeito (é idempotente).
3. Confira no Portainer, ou na VPS, com `docker service ls`: todos `1/1`, o `airflow-init` como concluído. O site em `FRONTEND_HOST`, a API em `API_HOST`, o Airflow (usuário `admin`, senha `AIRFLOW_ADMIN_PASSWORD`) e o MLflow (usuário e senha de `MLFLOW_ADMIN_*`) respondem; os dois últimos só a partir das origens de `ADMIN_ALLOWED_CIDRS`.
4. Para conferir a leitura do backend: `GET /forecast/figures/<modelo>/<arquivo>.png` devolve 200 `image/png`.

### 6. Produção

O stack `atlas-prod` é o mesmo arquivo lido da branch `main`, com `ATLAS_ENV=prod`, `IMAGE_TAG=X.Y` (a versão publicada, **nunca** a tag móvel `hml`), os hosts e secrets `atlas_prod_...` próprios. O deploy de produção só é acionado por tag `vX.Y` em `main`, depois da aprovação do Environment `prod`. Conferência: `docker service ls --format '{{.Name}} {{.Image}}'` deve mostrar só tags de versão nos serviços do `atlas-prod`.

## Jupyter de exploração (hml)

O Jupyter do stack roda a imagem `ml-notebook` (mesmas versões do Airflow) em `https://jupyter-hml.contovisual.com.br`, com **senha e TLS e sem lista de IPs**. É um **caderno isolado**: não tem Docker secret, credencial do Google Cloud, usuário do MLflow nem acesso à rede interna do stack, e não vê nenhum dado do Atlas. Quem quiser dados baixa um arquivo e o sobe para a pasta de trabalho, ou digita uma credencial na própria sessão e a apaga ao terminar. Não há conta de serviço, IAM nem secret para criar.

**Por que a proteção é assim.** Sem lista de IPs, a tela de login fica na internet. O que limita o estrago: o Jupyter não alcança nada do projeto, o proxy limita as tentativas (429), a senha é longa com hash argon2, e o terminal fica desligado. Se o risco incomodar, a lista de IPs entra com um middleware `ipallowlist`, como no Airflow e no MLflow.

### 1. DNS

Registro `A` de `jupyter-hml` para o **mesmo IP do `atlas-hml`** (hoje `37.27.80.107`), **só como DNS, sem o proxy do Cloudflare** (nuvem cinza): com proxy, o Traefik só vê o IP do Cloudflare e o limite de tentativas passa a valer para todo mundo junto. Sem o registro, o certificado do Let's Encrypt não é emitido. Confira:

```bash
nslookup atlas-hml.contovisual.com.br       # o IP do servidor de hml
nslookup jupyter-hml.contovisual.com.br     # tem de devolver o mesmo IP (e não os do Cloudflare)
```

### 2. Senha: gerar o hash

A senha não vai para o stack, só o **hash** (argon2). Escolha uma senha longa e aleatória, de pelo menos 20 caracteres (o login fica na internet), guarde-a num gerenciador (perdê-la significa gerar outro hash) e gere o hash:

```bash
# pede a senha duas vezes e imprime o hash (argon2:...); o uv baixa o jupyter-server só para este comando
uv run --with jupyter-server python -c "from jupyter_server.auth import passwd; print(passwd())"
```

### 3. Variáveis do stack

No Portainer (Stacks › atlas_epidemiologico_hml › Environment variables) e no seu `.env.hml`:

| Variável | Valor |
|---|---|
| `JUPYTER_HOST` | `jupyter-hml.contovisual.com.br` |
| `JUPYTER_REPLICAS` | `1` (`0` desliga o serviço) |
| `JUPYTER_PASSWORD_HASH` | o hash do passo 2 |

O hash tem `$`. **No Portainer cole o valor cru, sem aspas.** Num arquivo `.env` lido por shell, use aspas simples. Se o valor chegar estragado, o serviço não sobe e o log diz que o valor não parece um hash. Variáveis que **não valem mais** e podem ser apagadas do stack: `JUPYTER_TOKEN` e `JUPYTER_PORT` (só do dev), `JUPYTER_MLFLOW_USERNAME` e `JUPYTER_MLFLOW_PASSWORD`.

O `atlas-prod` não precisa de nada para o Jupyter existir no stack, mas sem a `JUPYTER_PASSWORD_HASH` o deploy de prod falha. Defina `JUPYTER_REPLICAS=0` e um hash qualquer até haver um host de prod.

### 4. Implantar

Publique a imagem (`ml.yml` em `hml` gera `atlas-epidemiologia-ml-notebook:hml`) e redeploy o stack no Portainer. Se o serviço não subir: `docker service logs atlas_epidemiologico_hml_jupyter --tail 50`.

### 5. Conferir

| O que | Como | Esperado |
|---|---|---|
| DNS | `nslookup jupyter-hml.contovisual.com.br` | o IP do servidor, não o do Cloudflare |
| Certificado | abrir `https://jupyter-hml.contovisual.com.br` | tela de login, certificado válido |
| Senha | entrar com a senha certa e com uma errada | entra / é negada |
| Limite de tentativas | `for i in $(seq 1 60); do curl -s -o /dev/null -w '%{http_code}\n' https://jupyter-hml.contovisual.com.br/login; done` | passa a responder `429`; o uso normal não é afetado |
| Terminal | abrir um terminal pela interface | recusado |
| Sem o hash | subir o serviço sem `JUPYTER_PASSWORD_HASH` | o deploy não sai (a variável é obrigatória) |
| Isolado | num notebook: `import socket; socket.create_connection(("mlflow", 5000), 3)` e o mesmo para `scheduler`, `postgres`, `redis` | falha (nome não resolve) |
| Versões | `pip list` no Jupyter e no Airflow | `atlas_ml` e as bibliotecas de ML iguais |
| Notebook de modelo | subir um parquet e rodar o `catboost` à mão | roda; as runs do MLflow ficam numa pasta local |

### 6. Rotação e desligar

- **Senha:** gere outro hash (passo 2), troque `JUPYTER_PASSWORD_HASH` no Portainer e no `.env.hml` e redeploy.
- **Desligar:** `JUPYTER_REPLICAS=0` e redeploy; os outros serviços não mudam. Para remover de vez, apague o registro DNS e os volumes `jupyter_work` e `jupyter_hf_cache`.

## Fluxo diário do Brasil (etl_brasil)

- **Quando:** todo dia às **03h00 de Brasília**, só em hml e prod (`ATLAS_ENV`). Em dev a DAG `etl_brasil` roda só à mão.
- **O que faz:** ingestão do SINAN (`ingestao_sinan_brasil`, espera até 3 h por dados novos) → dbt (`dbt_brasil`, só se a bronze mudou) → treino dos 6 modelos com a base inteira (`atlas_dengue_forecast_br`, só se a gold mudou desde os modelos vigentes) → exportação para o BigQuery. Na maioria dos dias não há dado novo e o fluxo termina em minutos.
- **Recursos na VPS:** o treino roda dentro do scheduler, limitado a 3 CPUs e 3,5 GB no stack; o pool `atlas_treino` (criado pelo `airflow-init`) deixa um treino pesado por vez (LSTM, Bayesiano ou Chronos), com `ATLAS_THREADS=2` e até 3 h por treino. O MLflow roda com 1 worker (`MLFLOW_WORKERS`). Medição de 18/11/2026: o nó usava ~5,7 GB sem treino, ~2 GB deles de outros stacks.
- **Primeira execução (base inteira):** no Airflow, dispare `etl_brasil` com `{"forcar_treino": true}`. Acompanhe em Grid: as três etapas em sequência; o treino leva horas. No MLflow do ambiente aparecem 24 runs (6 modelos × 4 horizontes) com `atlas.data_version` da gold completa; depois da exportação, o site mostra as 27 UFs. Durante o treino, confira a memória do nó (por exemplo, `docker stats --no-stream`) e se o site e a API seguem respondendo.
- **Forçar:** `{"forcar_dbt": true}` refaz a modelagem; `{"forcar_treino": true}` treina mesmo sem gold nova. Cada DAG também pode ser disparada sozinha.

## Atualizar, conferir, diagnosticar e voltar atrás

Tudo abaixo foi exercitado em um Portainer 2.45.3 real, criando o stack pelo repositório.

### Atualizar o stack

- **Pelo webhook:** o CI chama o webhook do stack depois de cada imagem publicada. À mão: `curl -fsS -X POST "<URL do webhook>"` responde 204 e o Portainer refaz o deploy com a definição que está na branch.
- **Pelo Portainer:** Stacks › `atlas-hml` › **Pull and redeploy** (com *re-pull image* para baixar de novo as imagens de tag móvel). Para mudar só uma variável: Editor › Environment variables › **Update the stack**.
- A sincronização por intervalo continua desligada; só o webhook ou o botão atualizam.

### Conferir o commit lido

O Portainer mostra o commit do stack na página dele. Compare com o da branch:

```bash
git ls-remote https://github.com/cnx-anselmooliveira/atlas_epidemiologico refs/heads/hml | cut -c1-7
```

Os sete primeiros caracteres precisam ser os mesmos. O Portainer atualiza o campo alguns segundos **depois** do deploy; se ainda estiver diferente, espere e recarregue.

### Quando o deploy falha

O Portainer não devolve erro na criação: o stack fica registrado com status **Failed** e a mensagem aparece na página dele (por exemplo `required variable IMAGE_TAG is missing a value`). Nada é implantado. Corrija a variável em Editor › Environment variables e reimplante; se preferir, apague o stack e crie de novo.

Depois do deploy, o diagnóstico é por serviço:

```bash
docker stack ps atlas-hml --no-trunc                 # estado e erro de cada tarefa
docker service logs atlas-hml_<serviço> --tail 50    # logs (serviços: postgres, mlflow, airflow-init, airflow-api-server, ...)
```

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `required variable ... is missing` | variável obrigatória sem valor | preencher no ambiente do stack |
| `secret not found` | Docker secret não criado | criar `atlas_hml_*` (passo 3) |
| `network ... not found` | rede `network_public` inexistente | criar a rede overlay do Traefik |
| `no suitable node` | `PLACEMENT_ROLE` sem nó compatível | ajustar a variável ou o nó |
| `No such image` / `pull access denied` | tag `hml` não publicada, ou sem login no DockerHub | publicar a imagem (workflow) e conferir `IMAGE_TAG` |
| `unhealthy container` (exit 137) | serviço não ficou saudável a tempo | ver o log do serviço; o MLflow leva até uns 4 minutos na primeira subida (migra os bancos), e o stack já espera isso |
| backend em 0/1 com `invalid_grant` ou `DefaultCredentialsError` | chave de `atlas_hml_backend_sa` inválida ou sem permissão | recriar o secret com a chave de leitura certa |

### Voltar atrás

1. **Automático:** nas atualizações, os serviços com `failure_action: rollback` voltam sozinhos para a versão anterior quando a nova não fica saudável.
2. **Pelo Git (o caminho preferido):** reverta o commit do arquivo (`git revert`), promova pelo fluxo normal de PR e reimplante.
3. **Emergência, sem esperar o PR:** o Portainer não aceita hash de commit como referência; use uma tag. Crie uma tag temporária no commit bom e aponte o stack para ela:
   ```bash
   git tag rollback-hml <commit-anterior> && git push origin rollback-hml   # o nome não pode começar com "v"
   ```
   No Portainer, em Stacks › `atlas-hml` › Editor, troque **Repository reference** para `refs/tags/rollback-hml` e faça o redeploy. Volumes (banco, logs) e secrets não mudam. Depois do conserto, volte a referência para `refs/heads/hml` e apague a tag (`git push origin :refs/tags/rollback-hml`).
4. **Um único serviço:** `docker service rollback atlas-hml_<serviço>` desfaz só a última atualização dele.

## Fluxo de promoção dev → hml → main

A produção é a **`main`** (não existe branch `prod`): `atlas-hml` lê a branch `hml` e `atlas-prod` lê a `main`, as duas com o caminho `docker-compose.yml`.

1. Trabalho em `dev`; cada push publica as imagens com tag `dev` (sem deploy). O `ci.yml` roda nos PRs e nos pushes para `hml` e `main`, e antes de qualquer publicação de imagem.
2. **Promover para hml:** PR `dev` → `hml`. No merge, os workflows das imagens alteradas publicam `hml` e chamam o webhook do Environment `hml`.
3. **Versão:** PR `hml` → `main`, depois a tag `vX.Y` em `main`. O workflow publica `X.Y` (imutável), espera a aprovação do Environment `prod` e chama o webhook de prod. Uma tag fora de `main` é recusada.
4. **Merge com commit de merge**, nunca squash nem rebase: o squash cria commits novos que não são ancestrais de `dev`, e o PR seguinte volta a listar tudo como diferença.

### O que o CI barra em um PR para hml ou main

| Job | Regra |
|---|---|
| `promocao` | `hml` só recebe PR de `dev`; `main` só recebe PR de `hml`. Qualquer outra origem falha explicando o fluxo. |
| `stack` | `docker-compose.yml`, `.env.example` e `platform/postgres/init-databases.sh` existem; `docker stack config` valida para hml (tag `hml`) e prod (tag de versão); sem `latest`, sem porta publicada, sem `build`, secrets externos, só imagens do projeto, `postgres` e `redis`. Roda também com `bash platform/ci/check-stack.sh`. |
| `secrets` | nenhum valor literal de credencial no `docker-compose.yml` e em `deploy/`, nenhuma variável do stack fora do `.env.example`. |
| `escopo` | decide entre a via rápida e o pipeline completo pelos arquivos alterados (ver abaixo). |
| `ci-ok` | passa só se todos os jobs que deviam rodar passaram (`promocao` pulado só é aceito fora de PR; os jobs dispensados, só na via rápida). É o único check exigido na proteção. |

### Via rápida do CI (DAGs, notebooks e docs)

Um PR ou push em que **todos** os arquivos alterados são de `airflow/dags/` (exceto `utfpr_dengue/pyproject.toml` e `uv.lock`), `airflow/tests/`, `ml/notebooks/`, `openspec/`, `docs/` ou `*.md` roda na via rápida:

- **Roda:** lint, verificação dos notebooks, testes das DAGs (na imagem `:hml` publicada, com as DAGs, os testes e os notebooks do commit montados), segredos, OpenSpec, stack e promoção.
- **Não roda:** o build das imagens, o e2e da plataforma, o frontend, o backend e os testes do pacote `ml`.
- **Por que é seguro:** DAGs e notebooks chegam a hml pelo git-sync, sem imagem nova, então nada do que a via rápida pula mudou. Qualquer arquivo fora da lista (`ml/src`, Dockerfile, workflow, dependência) leva ao pipeline completo. A chamada pela publicação de imagens é sempre completa.
- **Decisão:** `platform/ci/escopo.sh` (casos em `platform/ci/test-escopo.sh`). Para ver o que um diff faria: `git diff --name-only origin/hml...dev | bash platform/ci/escopo.sh`.
- **Antes do PR:** `bash platform/ci/testar-dags.sh` roda os mesmos testes de DAG localmente, em menos de 1 minuto.
- **Imagens:** mudar só notebooks também não dispara o `ml.yml`. O Jupyter de hml recebe os notebooks novos no próximo build da imagem `ml-notebook`.

### Proteção das branches `hml` e `main` (Settings › Branches)

| Configuração | Esperado |
|---|---|
| Exigir PR antes do merge | ligado, **sem** exigir aprovação (um só mantenedor) |
| Check obrigatório | `ci-ok`, com a branch em dia |
| Valer para administradores | ligado |
| Push direto, force-push e exclusão | bloqueados |
| Merge do repositório (Settings › General) | só **Create a merge commit**; squash e rebase desligados; "delete branch on merge" desligado (apagaria `dev` e `hml`) |

Para conferir: `gh api repos/cnx-anselmooliveira/atlas_epidemiologico/branches/<hml|main>/protection` e `gh api repos/cnx-anselmooliveira/atlas_epidemiologico --jq '{merge_commit: .allow_merge_commit, squash: .allow_squash_merge, rebase: .allow_rebase_merge}'`. O `.github/CODEOWNERS` pede o mantenedor para o stack, o `.env.example`, `platform/postgres/`, `deploy/` e os workflows.

### Conferência de produção

Depois de implantar o `atlas-prod`, todos os serviços do stack devem usar tag de versão: `docker service ls --format '{{.Name}} {{.Image}}'` não pode mostrar `:hml` nem `:dev`. O CI já impede um valor fixo no arquivo e só aciona o deploy de produção por tag em `main`; o valor de `IMAGE_TAG` no Portainer só você vê.

### Emergência

Um conserto urgente também passa por `dev` e `hml`. Se for impossível esperar, o administrador pode desligar a proteção da branch por um momento (Settings › Branches), aplicar a mudança e **religar na hora**; registre o motivo no PR seguinte.

## Desenvolvimento local

- Chaves em `platform/secrets/` e senhas no `.env` da raiz: ambos são ignorados pelo Git e entram nos containers só em runtime, como volume somente leitura. Nunca são copiados para uma imagem.
- Não deixe a chave solta na raiz do repositório (`ppgcc-dengue-project.json`): use `platform/secrets/`.
- O `AIRFLOW__API_AUTH__JWT_SECRET` e a senha de dev do `compose.dev.yml` valem **só** para a máquina local.

## Proteções contra vazamento

1. **Hook local** (uma vez por clone): `git config core.hooksPath .githooks`. Ele roda `platform/ci/check-secrets.sh --staged` antes de cada commit.
2. **CI**, job `secrets` (em todo push e PR, e dentro do `ci-ok`):
   - `check-secrets.sh --all` barra nomes proibidos (`.env`, `*.pem`, `*.key`, `secrets/`, chaves de service account), conteúdos com formato de credencial (chave privada, JSON de service account, tokens do GitHub e do DockerHub, URL de webhook do Portainer), valor literal em campo de credencial do `docker-compose.yml` e de `deploy/`, variável de compose ou stack ausente do `.env.example` e valor real no próprio exemplo;
   - gitleaks no histórico inteiro (`.gitleaks.toml`, com as exceções conhecidas).
3. **`.gitignore` e `.dockerignore`:** as mesmas famílias de arquivo ficam fora do Git e fora do contexto de build.
4. **GitHub:** secret scanning e push protection ligados no repositório.

## Se uma credencial vazar

1. Revogue a chave na hora (GCP IAM › Service accounts › Keys, ou o token no DockerHub/GitHub/Portainer). Apagar o commit **não basta**: o repositório é público e a chave já pode ter sido copiada.
2. Crie uma nova e atualize nos lugares da tabela acima.
3. Só depois limpe o histórico, se necessário.
