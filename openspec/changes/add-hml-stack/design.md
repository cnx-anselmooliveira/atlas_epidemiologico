# Design

## Context

Observado no repositório:

- `platform/compose.dev.yml` define a plataforma completa, mas com `build`, volumes de código (`../airflow/dags`, `../ml/src`), portas em `127.0.0.1` e `depends_on` com `service_healthy`.
- `deploy/app.stack.yml` é Swarm (`deploy:`, rede overlay `atlas_internal`, rede externa `network_public`, rótulos do Traefik com `letsencryptresolver`) e cobre só `frontend`, `backend` e `redis`.
- A VPS já foi pensada: `airflow/config/vps.env` (FAB Auth Manager, sem expor config), `MLFLOW_INSTALLATION` aceita `dev|vps`, `MLFLOW_AUTH` com basic-auth exige `MLFLOW_AUTH_DATABASE_URI`, admin e chave CSRF, e `platform/postgres/init-databases.sh` aceita vários bancos do Airflow (`airflow_hml airflow_prod`).
- A imagem do Airflow embute as DAGs, o dbt e o `atlas_ml`; o `compose.dev.yml` fixa `gs://ppgcc-bucket/cosmos_cache/dev` e `.../dbt_docs/dev`.
- `airflow/config/init.sh` é idempotente e sabe criar o admin no FAB.
- `platform/.env.example` não traz `BACKEND_PORT`, `FRONTEND_PORT`, `MLFLOW_PORT` nem `AIRFLOW_PORT`, que o compose lê. `frontend/.env.example` existe; o backend não tem exemplo.
- O CI já tem o job `secrets` (`check-secrets.sh` e gitleaks) e o `.gitignore` libera `!.env.example`.

## Goals / Non-Goals

**Goals:**
- Um arquivo de stack que sobe o Atlas em hml e prod, só com variáveis.
- Subida confiável no Swarm sem `depends_on`.
- Credenciais fora do arquivo, do Git e das imagens.
- Exemplos de variáveis completos e conferidos pelo CI.

**Non-Goals:**
- Alta disponibilidade, réplicas do Airflow ou multi-nó (um nó, `LocalExecutor`).
- Migrar a chave do `app` de variável para Docker secret em prod (evolução já registrada).
- Observabilidade (Prometheus, Loki) e backup automatizado do Postgres; ficam como mudança própria, mas o design deixa um volume nomeado para o dump.
- Criar a VPS, o DNS ou o Traefik.

## Decisions

1. **Arquivo único `docker-compose.yml` na raiz, dois stacks.** `atlas-hml` e `atlas-prod` usam o mesmo arquivo; o que muda são `ATLAS_ENV`, `IMAGE_TAG`, os hosts, os bancos e os secrets. Alternativa descartada: um arquivo por ambiente, porque duplica tudo e hml deixa de provar o que vai para prod. Alternativa descartada: manter `app.stack.yml` e `platform.stack.yml` separados, porque rede, hosts e credenciais ficariam repetidos e o site precisa do backend na mesma rede. **Local:** na raiz, não em `deploy/` (decisão do usuário), com o nome `docker-compose.yml`, o caminho padrão do Portainer, igual em todas as branches. O compose de desenvolvimento continua em `platform/compose.dev.yml` e é sempre chamado com `-f`; rodar `docker compose up` sem `-f` na raiz tentaria subir o stack de hml, mas as variáveis obrigatórias (`${IMAGE_TAG:?}`, senhas, `ATLAS_ENV`) fazem a tentativa falhar em voz alta. O arquivo na raiz entra no contexto de build das imagens que usam `.` (Airflow), então o `.dockerignore` da raiz o exclui; ele não tem credencial de qualquer forma.

2. **Formato Swarm, não `docker compose` puro.** A VPS já roda Swarm com Traefik (rótulos em `deploy.labels`, rede externa). O `docker compose` do dev continua só para desenvolvimento. Consequências: sem `build`, sem `depends_on`, `restart_policy` em `deploy`.

3. **Ordem de subida por espera, não por dependência.** `airflow-init` roda como serviço com `restart_policy: on-failure` (máximo de tentativas) e `replicas: 1`; scheduler, dag-processor, triggerer e api-server iniciam com `airflow db check-migrations --migration-wait-timeout` antes do comando principal. O MLflow tenta conectar ao Postgres com reinício em falha. O backend e o frontend usam `update_config: order: start-first` e rollback em falha, e o frontend degrada sem o backend (já implementado). Alternativa descartada: um script de entrada que sobe tudo, porque esconderia falhas do Swarm.

4. **Postgres inicializado por Docker config.** O script `init-databases.sh` (caminho relativo `./platform/postgres/init-databases.sh`, a partir da raiz onde está o stack) entra por `configs:` (arquivo do repositório, lido na criação do stack pelo Portainer a partir do Git) em `/docker-entrypoint-initdb.d/`. Requer implantar o stack **a partir do repositório**, não colando o YAML no editor; documentado. As senhas dos usuários `mlflow` e `airflow` são variáveis distintas. Um stack por ambiente tem o seu Postgres e o seu volume (`pgdata`), com bancos `airflow`, `mlflow` e `mlflow_auth`; a divisão `airflow_hml`/`airflow_prod` do `vps.env` só valeria para um Postgres compartilhado, que não é adotado aqui (decisão registrada).

5. **Credenciais.** Chaves de service account como **Docker secrets** (`training_sa`, `mlflow_sa`, `backend_sa`), montadas em `/run/secrets/<nome>`; `GOOGLE_APPLICATION_CREDENTIALS`, `DBT_BQ_KEYFILE` e o `key_path` da Connection apontam para elas. Senhas e tokens por variáveis de stack do Portainer. O backend usa a conta de leitura própria (já decidida na `add-hml-cicd-images`). Docker secrets são imutáveis: trocar uma chave é criar `nome_v2` e atualizar o stack; o README descreve.

6. **Instalação do MLflow por ambiente.** `entrypoint.sh` aceita `dev|hml|prod` (mantendo `vps` por compatibilidade, tratado como `prod`); o stack passa `MLFLOW_INSTALLATION=${ATLAS_ENV}`. O cache do Cosmos e os docs do dbt usam `gs://${BUCKET}/cosmos_cache/${ATLAS_ENV}` e `.../dbt_docs/${ATLAS_ENV}` por variável de ambiente do stack. Assim hml e prod nunca dividem prefixo.

7. **Airflow com FAB.** `AIRFLOW__CORE__AUTH_MANAGER` do `vps.env` (FAB) vem como arquivo de ambiente do stack (Docker config) ou variáveis explícitas; o `init.sh` já cria o admin. O `AIRFLOW__API_AUTH__JWT_SECRET` e a fernet key são variáveis obrigatórias distintas por ambiente. O diretório `shared` e os logs são volumes nomeados no mesmo nó, com restrição de posicionamento (`node.hostname`) para garantir que todos os serviços do Airflow rodem no nó que tem os volumes.

8. **Traefik e hosts.** Rótulos como no `app.stack.yml`, com hosts por variável (`FRONTEND_HOST`, `API_HOST`, `AIRFLOW_HOST`, `MLFLOW_HOST`; sugestão `hml.dengue...`, `api-hml.dengue...`). As interfaces do Airflow e do MLflow ficam atrás da autenticação própria e de um middleware `ipallowlist` com `ADMIN_ALLOWED_CIDRS`. Premissa registrada: expor as duas interfaces com essas proteções, em vez de só por túnel SSH; se o usuário preferir túnel, basta remover os rótulos.

9. **Portainer pelo GitHub e webhook do stack.** O stack é criado em Stacks › Add stack › **Repository** (URL do repositório, branch `hml`, caminho `docker-compose.yml`), com a sincronização por intervalo desligada e o **webhook do stack** ativado, baixando as imagens de novo no redeploy. O CI chama esse webhook depois de cada imagem publicada (uma chamada por workflow; chamadas repetidas só refazem o deploy com as mesmas imagens). Substitui os webhooks por serviço e a lista de URLs do Airflow. Alternativa descartada: sincronização por intervalo, porque o Portainer poderia implantar antes de a imagem de 10 GB terminar de subir e ficaria com a versão anterior; fica como contingência. O secret passa a ser um por Environment (`PORTAINER_WEBHOOK_STACK`, nos Environments `hml` e `prod`).

10. **Um `.env.example` na raiz e um `.env` local.** Decisão do usuário: só um exemplo e um `.env`. O arquivo tem grupos comentados (só dev local, stack hml e prod, segredos) e serve ao compose de dev (`--env-file` da raiz em `dev.ps1`), ao Portainer (carregar as variáveis do arquivo ou digitá-las) e ao site (`node --env-file=../.env` nos scripts de `npm run dev` e `start`). Variáveis que só existem em um ambiente ficam no grupo certo, com padrão seguro. `platform/.env.example` e `frontend/.env.example` são removidos. Um passo do `check-secrets.sh` extrai `${NOME}` de `docker-compose.yml` e `platform/compose.dev.yml` e falha se o nome não existir no exemplo, e confere que os valores do exemplo são vazios ou reconhecíveis (`troque-esta-senha`, hosts de exemplo). Alternativas descartadas: gerar o exemplo a partir do stack, porque os comentários de uso se perderiam; e dois exemplos (dev e hml), porque o usuário prefere um só.

11. **Promoção hml → prod.** O stack `atlas-prod` sai do mesmo arquivo com `IMAGE_TAG=X.Y` (tag imutável, nunca a móvel `hml`). O webhook de prod fica no Environment `prod` e exige aprovação. A tag móvel `hml` é atualizada pelos webhooks de serviço.

## Risks / Trade-offs

- **Swarm local não é a VPS.** Um Swarm de um nó valida sintaxe, secrets, configs, ordem de subida e health checks, mas não o Traefik nem o TLS. Os rótulos são validados por leitura e pelo primeiro deploy real.
- **Volumes locais no Swarm** prendem os serviços a um nó (Airflow compartilha `shared` e logs). Em troca, a topologia é simples. Quem migrar para multi-nó precisará de volume compartilhado.
- **Airflow e MLflow expostos** aumentam a superfície. Mitigações: FAB e basic-auth, lista de origens, `AIRFLOW__API__EXPOSE_CONFIG=False`, sem porta direta; a decisão pode ser revertida removendo os rótulos.
- **Stack criado a partir do Git** (necessário para o Docker config do Postgres e escolhido pelo usuário) liga o Portainer ao repositório público; sem credencial, mas a branch de implantação (`hml`) precisa ser a certa, e o `docker-compose.yml` em `hml` é o que vale. Se alguém mudar só esse arquivo, o redeploy é manual.
- **Um só `.env` para dev e stack** mistura variáveis de contextos diferentes; os grupos comentados e o padrão seguro de cada variável reduzem o risco de usar um valor de dev em hml.
- **Primeiro boot do Postgres** só executa os scripts com o volume vazio; mudar senha depois exige `ALTER ROLE`. O README descreve.
- **Imagem `airflow` grande** demora a baixar na primeira vez na VPS; `update_config` com `order: stop-first` nos serviços do Airflow evita dois schedulers ao mesmo tempo.
