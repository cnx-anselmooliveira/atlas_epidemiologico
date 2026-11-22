# Design

## Context

Motivação e escopo: ver `proposal.md`. Estado atual relevante:

- **Jupyter só em dev.** `platform/compose.dev.yml` (serviço `jupyter`, profile `notebook`) usa a imagem `ml` com o alvo `notebook`, porta em `127.0.0.1`, a chave `training-sa.json` e o token padrão `atlas`. O alvo `notebook` de `ml/Dockerfile` (JupyterLab sobre o venv do `atlas_ml`) passou a ser publicado como `atlas-epidemiologia-ml-notebook` (job em `ml.yml`).
- **Stack de hml.** `docker-compose.yml` (Swarm/Portainer) sobe Airflow, MLflow, API, site e Redis atrás do Traefik (`network_public`, certificado `letsencryptresolver`), com `ipallowlist` nos serviços administrativos. A rede `atlas_internal` liga os serviços entre si. Contas de serviço entram como Docker secrets.
- **Notebooks de modelo.** `ml/notebooks/<modelo>/` (change `self-contained-model-notebooks`) são autocontidos e leem os dados de uma consulta ao BigQuery **ou de um arquivo parquet**; sem `MLFLOW_TRACKING_URI`, o MLflow grava numa pasta local (`mlruns`). Dá para rodá-los no Jupyter só com um parquet subido à mão.
- **DNS (verificado em 22/11/2026).** `jupyter-hml.contovisual.com.br` já resolve para `37.27.80.107`, o servidor de hml, só como DNS (sem proxy do Cloudflare).
- **Variáveis.** A senha e o restante do ambiente de hml já ficam no `.env.hml` e nas variáveis do stack no Portainer.

## Goals / Non-Goals

**Goals:**
- Um Jupyter em `jupyter-hml.contovisual.com.br`, protegido por senha e TLS, com as versões do Airflow.
- **Zero integração:** nada de credenciais, secrets, rede interna nem dados do projeto dentro dele.
- Nada de segurança nova para operar: sem conta de serviço, IAM, secret ou usuário no MLflow.

**Non-Goals:**
- Lista de IPs (descartada pelo usuário) e autenticação por provedor externo (OAuth).
- Qualquer acesso do Jupyter a BigQuery, bucket, MLflow, Airflow, banco, Redis ou `git-sync`.
- Prod: o serviço fica pronto para o prod, mas o host de prod não entra agora.
- Executar o pipeline de produção pelo Jupyter.

## Decisions

### 1. Host, DNS e certificado
- Roteador do Traefik com a regra `Host(`${JUPYTER_HOST}`)`, `websecure`, `certresolver=letsencryptresolver`, porta interna 8888, na rede `network_public`. `JUPYTER_HOST` é variável do stack (hml: `jupyter-hml.contovisual.com.br`).
- Registro DNS `A` para `37.27.80.107` (o do `atlas-hml`), **sem o proxy do Cloudflare**: com proxy o Traefik só vê o IP do Cloudflare e o limite de tentativas passaria a valer para todos juntos. O Let's Encrypt só emite o certificado depois que o nome resolve. Conferência: `nslookup jupyter-hml.contovisual.com.br` devolve o IP do servidor.
- O Jupyter atrás de proxy precisa de websocket (o Traefik repassa) e do servidor configurado para aceitar os cabeçalhos do proxy (`trust_xheaders`) e acessos remotos (`allow_remote_access`).

### 2. Senha: hash em variável, sem token e sem secret
- O servidor usa o provedor de identidade por senha do Jupyter Server (`PasswordIdentityProvider`, `hashed_password`) lendo o hash da variável `JUPYTER_PASSWORD_HASH`; o token fica desligado (`token=""`).
- A variável guarda **só o hash** (argon2, gerado por `jupyter_server.auth.passwd`), nunca a senha. A senha em texto fica com quem a escolheu; perdê-la significa gerar outro hash e atualizar a variável. O hash não revela a senha nem no `docker service inspect`.
- **Sem padrão:** a configuração do servidor (na imagem) falha, com mensagem, se a variável faltar, estiver vazia ou não parecer um hash (uma senha em texto é recusada). No stack, o compose usa `${JUPYTER_PASSWORD_HASH:?...}`, então o deploy também não sai sem ela.
- Senha longa e aleatória (≥ 20 caracteres), porque o login fica na internet.
- **Cuidado com o `$`:** o hash argon2 contém `$`. No `.env.hml` ele vai entre aspas simples; no Portainer, no campo de variáveis, vai cru. Verificar na implementação que o valor chega intacto ao contêiner.

*Alternativas descartadas:* Docker secret com o hash (mais um objeto para criar e girar, sem ganho aqui, já que o hash não revela a senha); token por variável (aparece em texto no `docker service inspect` e o atual tem só 5 caracteres).

### 3. Sem lista de IPs: o que compensa
Por escolha do usuário, o login fica aberto à internet (só senha e TLS). As compensações, nesta ordem:
1. **Isolamento total (decisão 5):** quem entrar não alcança nenhum dado nem serviço do Atlas. Esse é o principal limite de dano.
2. **Limite de tentativas no proxy:** middleware `ratelimit` do Traefik por origem (média 10 por segundo, rajada 20), respondendo 429.
3. **Senha forte** (≥ 20 caracteres) e hash argon2, que torna cada tentativa cara.
4. **Terminal desativado:** sem shell pelo navegador.
5. **Contêiner contido e desligável** (decisão 6).
6. **Registro de acessos:** os logs do Traefik e do Jupyter mostram as tentativas.
Risco residual aceito: um atacante com a senha usa a CPU do contêiner (limitada) e vê só o que a pessoa subiu. Se incomodar, a lista de IPs entra com uma linha (`ipallowlist`).

### 4. Imagem e notebooks
- `ml.yml` publica o alvo `notebook` como `atlas-epidemiologia-ml-notebook` (`ATLAS_ML_EXTRAS=models`, mesmas tags: `dev`, `hml`, `X.Y`). `release.yml` e a tabela de imagens do `deploy/README.md` listam a imagem.
- O alvo `notebook` leva a configuração do servidor (senha por variável, terminal desligado, proxy aceito, `root_dir` no volume de trabalho, `allow_root` falso) e uma cópia de `ml/notebooks` em `/opt/atlas/notebooks`.
- **Semente do volume de trabalho:** ao subir, se o volume está vazio, o serviço copia os notebooks da cópia da imagem para ele. O clone do `git-sync` **não** é usado. O usuário edita só a cópia.
- Para rodar um notebook de modelo, a pessoa sobe um parquet com os dados (os notebooks já sabem ler parquet) e as runs do MLflow ficam numa pasta local do volume.

### 5. Sem integração com nada
O serviço `jupyter` do stack **não** recebe:
- Docker secrets (nem conta do Google, nem os de outros serviços);
- a rede `atlas_internal` (só a `network_public`, que o Traefik exige): não alcança MLflow, Airflow, banco nem Redis;
- variáveis de credencial (`GOOGLE_APPLICATION_CREDENTIALS`, `MLFLOW_TRACKING_*`, `GCP_PROJECT`) nem o volume `airflow_dags`.

Se a pessoa quiser dados do Google Cloud, ela os baixa e sobe, ou digita uma credencial dela na sessão e apaga depois. Nenhum dado de produto é compartilhado com o serviço. O `check-stack.sh` falha se o serviço ganhar secrets, a rede interna ou essas variáveis.

*Nota:* a rede `network_public` é compartilhada com outros stacks do Swarm na VPS; isso não dá ao Jupyter acesso a este stack, mas serviços de outros stacks nessa rede ficam alcançáveis. É uma propriedade da VPS, igual à dos demais serviços atrás do Traefik.

### 6. Serviço no stack e contêiner contido
- Serviço `jupyter` (imagem do `ml` notebook, tag `IMAGE_TAG`), rede só `network_public`, `replicas: ${JUPYTER_REPLICAS:-1}`, nó `PLACEMENT_ROLE`.
- `cap_drop: [ALL]`, `read_only: true` com `tmpfs` em `/tmp` e o volume de trabalho gravável, usuário não-root (`atlas`, uid 1000), limites de CPU e memória abaixo da folga da VPS (4 CPUs e 8 GB, com o scheduler em 3,5 GB), e `HF_HOME` num volume (cache do Chronos). O `no-new-privileges` **não** é aceito em serviços do Swarm.
- Variáveis do serviço: `JUPYTER_PASSWORD_HASH`, `JUPYTER_HOST` (rótulo), `JUPYTER_REPLICAS`, `ATLAS_THREADS`, `HF_HOME`. Nada de credencial de serviço.
- **`check-stack.sh`:** regras do serviço `jupyter`: sem porta publicada; **sem secrets**; **fora da rede `atlas_internal`**; sem variáveis de credencial (`GOOGLE_APPLICATION_CREDENTIALS`, `MLFLOW_TRACKING_*`); sem o volume `airflow_dags`; com `cap_drop`, `read_only` e usuário não-root; com o middleware de limite de tentativas.

### 7. Dev e higiene dos notebooks
- O Jupyter de dev segue o mesmo modelo: sem chave do Google e sem MLflow (só o que se sobe à mão), `JUPYTER_TOKEN` obrigatório (sem o padrão `atlas`), `ml/notebooks` montado, só em `127.0.0.1`.
- Verificação de notebooks sem saídas no CI e no hook local (`ml/notebooks/_ferramentas/verificar_sem_saidas.py`, só biblioteca padrão, com `--limpar`): o repositório é público, e saídas de células podem trazer dados.

## Risks / Trade-offs

- **[Login exposto à internet (sem lista de IPs)]** → o Jupyter não tem acesso a nada do projeto; limite de tentativas, senha ≥ 20 caracteres com hash argon2, terminal desligado, serviço desligável; a lista de IPs fica a uma linha de distância.
- **[Senha perdida]** → gerar outro hash e atualizar `JUPYTER_PASSWORD_HASH` (a receita fica no `deploy/README.md`).
- **[`$` do hash alterado pela interpolação do `.env` ou do compose]** → aspas simples no `.env.hml`; conferir o valor dentro do contêiner; a configuração do servidor recusa um valor que não pareça um hash, então o erro é visível.
- **[Let's Encrypt e limites de emissão]** → um certificado por host; não refazer o stack sem necessidade.
- **[Proxy do Cloudflare ligado por engano]** → o limite de tentativas passa a valer para todos juntos; conferir com `nslookup` que o nome devolve o IP do servidor.
- **[Pessoa guarda credencial ou dado sensível no volume do Jupyter]** → a orientação é apagar a credencial ao terminar; o volume é do Jupyter e some ao remover o serviço e o volume.
- **[Jupyter disputa CPU e memória com o Airflow na VPS]** → limites do serviço; um estouro reinicia só o Jupyter.
- **[Notebook com saída de dados indo ao repositório público]** → verificação de saídas no CI e no hook.
- **[Capacidade `jupyter-exploration-service` duplicada na `move-forecast-to-notebook-pipeline`]** → esta change é a versão válida; atualizar aquela com `openspec-update-change` para tirar o Jupyter dela.

## Migration Plan

1. DNS (já feito): `A` para o IP do `atlas-hml`, sem proxy.
2. Gerar o hash da senha (≥ 20 caracteres) e definir `JUPYTER_PASSWORD_HASH` no Portainer e no `.env.hml`; remover `JUPYTER_TOKEN`, `JUPYTER_PORT`, `JUPYTER_MLFLOW_USERNAME` e `JUPYTER_MLFLOW_PASSWORD` do stack, que não valem mais.
3. Publicar a imagem `ml-notebook` com a tag `hml` e atualizar o stack de hml.
4. Verificar: certificado válido, login com a senha, limite de tentativas, terminal recusado, e que de dentro do Jupyter o MLflow e o Airflow não são alcançáveis.
5. **Reversão:** `JUPYTER_REPLICAS=0` tira o serviço do ar; remover o registro DNS e o volume desfaz o resto.

## Open Questions

- **Limites do `ratelimit`:** a média e a rajada de partida (10 por segundo e 20) são um ponto de partida; ajustar depois de ver o uso real e os logs do Traefik.
- **Prod:** host e variável de prod ficam para quando fizer sentido ter exploração em prod.
