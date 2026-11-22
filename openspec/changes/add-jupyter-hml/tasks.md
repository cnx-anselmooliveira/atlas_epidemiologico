# Tasks

## 1. Imagem do Jupyter

- [x] 1.1 Ajustar `ml/docker/jupyter_server_config.py`: a senha vem do **hash na variável `JUPYTER_PASSWORD_HASH`** (no lugar do arquivo do secret), token desligado; falha com mensagem se a variável faltar, estiver vazia ou não parecer um hash; o modo de dev (`JUPYTER_TOKEN` obrigatório, sem padrão) continua; terminal desativado, `trust_xheaders`, `allow_remote_access`, `allow_root` falso; atualizar `ml/tests/test_jupyter_docker.py` (sem variável falha citando o nome, vazia falha, texto que não é hash falha, hash válido define a senha e o token vazio, terminal desativado)
- [x] 1.2 Tirar o clone do `git-sync` do semeador (`ml/docker/semear_notebooks.py`): o volume vazio recebe só a cópia da imagem em `/opt/atlas/notebooks`, e volume com trabalho não é sobrescrito; atualizar os testes do semeador e reconstruir a imagem
- [x] 1.3 Verificar a imagem rodando (`docker run` com `--read-only`, `--cap-drop ALL` e o volume de trabalho): sem a variável do hash o contêiner não sobe e mostra o motivo; com um hash de teste o login com a senha certa entra e com a errada é negado; a API de terminais recusa; o usuário do processo não é root; o `$` do hash chega intacto
- [ ] 1.4 Publicar o alvo `notebook` como `atlas-epidemiologia-ml-notebook`: segundo job em `.github/workflows/ml.yml` (alvo `notebook`, `ATLAS_ML_EXTRAS=models`, mesmas tags), `ml-notebook` na lista de imagens de `release.yml` e na tabela de imagens do `deploy/README.md`; verificar com `actionlint` e lendo o YAML, e depois com a primeira execução do workflow

## 2. Serviço no stack

- [x] 2.1 Simplificar o serviço `jupyter` do `docker-compose.yml`: sem `secrets`, sem a rede `atlas_internal` (só `network_public`), sem `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT`, `MLFLOW_TRACKING_*`, `ATLAS_FORECAST_EXPERIMENT` e sem o volume `airflow_dags`; `JUPYTER_PASSWORD_HASH: ${JUPYTER_PASSWORD_HASH:?...}`; tirar os secrets `jupyter_sa` e `jupyter_password_hash` do topo; manter volumes de trabalho e do Hugging Face, `cap_drop`, `read_only`, `tmpfs`, limites, rótulos do Traefik e o middleware de limite de tentativas; verificar com `docker stack config` para hml e prod
- [x] 2.2 Atualizar o `.env.example`: tirar `JUPYTER_MLFLOW_USERNAME`, `JUPYTER_MLFLOW_PASSWORD` e `JUPYTER_TOKEN` do stack, manter `JUPYTER_HOST` e `JUPYTER_REPLICAS` e declarar `JUPYTER_PASSWORD_HASH` sem valor (com a nota das aspas simples por causa do `$`); verificar com `bash platform/ci/check-secrets.sh --all`
- [x] 2.3 Reescrever as regras do `jupyter` em `platform/ci/check-stack.sh`: sem porta publicada, **sem secrets**, **fora da `atlas_internal`**, sem variáveis de credencial (`GOOGLE_APPLICATION_CREDENTIALS`, `MLFLOW_TRACKING_*`) nem o volume `airflow_dags`, com `cap_drop`, `read_only`, usuário não-root e o middleware de limite de tentativas; atualizar `platform/ci/test-check-stack-jupyter.sh` com um caso negativo por violação e conferir que todos são recusados

## 3. Dev e higiene dos notebooks

- [x] 3.1 Alinhar o Jupyter de dev em `platform/compose.dev.yml` ao hml: sem a chave do Google e sem variáveis do MLflow, `JUPYTER_TOKEN` obrigatório (sem o padrão `atlas`), `ml/notebooks` montado, só em `127.0.0.1`; atualizar `.env.example`, `platform/README.md` e a documentação de dev; verificar com `docker compose config` e vendo que sem o token o serviço não sobe
- [x] 3.2 Verificar notebooks sem saídas com uma ferramenta própria, só da biblioteca padrão (`ml/notebooks/_ferramentas/verificar_sem_saidas.py`, com `--limpar`), no `ci.yml` (falha apontando o arquivo e a célula) e no `.githooks/pre-commit`; verificar com um notebook de teste com saída (o CI falha) e com os notebooks do repositório (passam)

## 4. Documentação

- [x] 4.1 Reescrever a seção "Jupyter de exploração (hml)" do `deploy/README.md` na versão mínima: o que o Jupyter é e o que ele **não** tem; o DNS direto, sem proxy do Cloudflare, e a conferência com `nslookup`; como gerar o hash da senha (argon2) e defini-lo em `JUPYTER_PASSWORD_HASH` no Portainer e no `.env.hml` (aspas simples, por causa do `$`); como subir dados à mão e a orientação de nunca deixar credencial no volume; rotação da senha; `JUPYTER_REPLICAS=0` para desligar; os testes a rodar. Tirar as linhas dos Docker secrets do Jupyter das tabelas do README e a conta, o IAM, o sandbox e o usuário do MLflow

## 5. Validação em hml

- [x] 5.1 DNS: `jupyter-hml.contovisual.com.br` resolve para o IP do servidor, sem proxy do Cloudflare (conferido com `nslookup` em 22/11/2026)
- [ ] 5.2 Gerar o hash, definir `JUPYTER_PASSWORD_HASH` no Portainer e no `.env.hml`, remover as variáveis que não valem mais, publicar a imagem com a tag `hml` e atualizar o stack; verificar o certificado válido na URL, o login com a senha, a recusa da senha errada, o limite de tentativas (dezenas por segundo recebem 429, e o uso normal não), o terminal recusado, e que o serviço não sobe sem a variável
- [ ] 5.3 Verificar o isolamento: de dentro do Jupyter, o MLflow, o Airflow, o banco e o Redis não são alcançáveis; rodar um notebook de modelo na mão (por exemplo o `catboost`) sobre um parquet subido e conferir que as versões do `atlas_ml` batem com as do Airflow; registrar o resultado em `docs/referencias/jupyter-hml.md`

## Workflow follow-up

- Atualizar a `move-forecast-to-notebook-pipeline` com `openspec-update-change`: tirar dela o Jupyter (spec `jupyter-exploration-service`, decisão 9 do design e o grupo 7 de tarefas), porque esta change é a versão válida (senha por hash em variável, TLS, isolado, sem lista de IPs).
- Escolher uma senha longa e aleatória (≥ 20 caracteres) e guardá-la num gerenciador, porque só o hash fica no stack.
- Combinar a ordem dos merges com a `add-hml-stack` e a `add-hml-cicd-images`, porque as três tocam `docker-compose.yml`, `check-stack.sh` e `deploy/README.md`.
- Arquivar a mudança quando o Jupyter de hml estiver no ar e validado.
