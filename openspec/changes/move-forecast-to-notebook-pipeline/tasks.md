# Tasks

## 1. Dependências e contrato do pacote

- [x] 1.1 Adicionar `papermill` e `ipykernel` ao grupo `models` de `ml/pyproject.toml` e atualizar o `ml/uv.lock`; verificar com `uv sync --extra models` e `uv run --extra models python -c "import papermill, ipykernel"`
- [x] 1.2 Expor `NOTEBOOK_API` (inteiro) em `atlas_ml.forecast`; verificar com um teste que lê o valor e que a verificação de versão do notebook (tarefa 2.2) falha quando a exigida é maior que a instalada

## 2. Notebook do pipeline

- [x] 2.1 Criar `atlas_ml/forecast/notebook.py` com o executor do notebook (papermill com `log_output=False`, leitura obrigatória de `result.json`, notebook executado em `out_dir`) e a função que anexa o notebook executado à run do MLflow; verificar com testes: resultado ausente falha com a mensagem do arquivo esperado, e o notebook anexado aparece como artefato da run
- [x] 2.2 Criar `ml/notebooks/forecast_pipeline.ipynb` (célula `parameters`, verificação de `NOTEBOOK_API`, validação de `step` e `model` com a lista aceita, passos `prepare`, `train` e `compare` chamando `forecast.dataset.prepare`, `forecast.base.run_model` e `forecast.compare.compare`, configuração de threads, SHA e MLflow que o `pipeline.py` fazia, `painel_parquet` opcional, tags `atlas.notebook_sha` (e `atlas.git_sha`, que a plataforma já grava), gravação de `result.json`); verificar executando o notebook com `papermill` num painel sintético e conferindo o `result.json` de cada passo
- [x] 2.3 Gravar `atlas.notebook_sha` a partir do destino do link do `git-sync` (variável `ATLAS_NOTEBOOK_SHA`, sem `git` na imagem; `local` fora do clone); verificar com teste que o valor sai do nome da árvore apontada pelo link e que, sem link, vira `local`
- [x] 2.4 Testar o notebook no CI em `ml/tests/forecast/test_notebook_pipeline.py`: `prepare` (com `painel_parquet`), `train` de um modelo leve e `compare` sobre o painel sintético e MLflow temporário, sem BigQuery; verificar `uv run pytest -m models` verde, com falha se uma célula levantar erro, e um teste de `step` e `model` inválidos que não cria run
- [x] 2.5 Documentar o notebook em `ml/README.md` (parâmetros, passos, como rodar à mão com `papermill`, `painel_parquet`, tags de versão); verificar executando o comando documentado

## 3. DAG executando o notebook

- [ ] 3.1 Criar a tarefa `configuracao` com o diretório por execução (`ATLAS_PIPELINE_DIR`, padrão `/tmp/atlas`, nome normalizado do `run_id`) e o SHA do notebook de partida, e a tarefa final `limpar` (`trigger_rule="all_done"`) que remove o diretório; verificar com teste `DagBag` (ordem e regra de disparo) e com teste da função de limpeza com sucesso e com falha
- [ ] 3.2 Trocar `prepare`, `treinar` e `comparar` de `atlas_dengue_forecast_br.py` para executar o notebook pelo executor da tarefa 2.1 (mesmo `external_python`, pool, timeouts, horizontes e `trigger_rule`), comparando o SHA do notebook com o de partida e falhando com mensagem clara se mudou; verificar com `airflow/tests/test_dags.py` (mesmas tarefas, dependências e pools de antes) e com teste do falha-por-SHA
- [x] 3.3 Implementar a tarefa genérica de ingestão de arquivo (lê parquet ou JSON de `out_dir` e grava no MLflow ou no BigQuery, idempotente pelo identificador da run, falha sem escrever quando o arquivo falta); verificar com testes de reexecução sem duplicar linhas e de arquivo ausente, com cliente BigQuery simulado
- [ ] 3.4 Definir `ATLAS_NOTEBOOKS_DIR` e `ATLAS_PIPELINE_DIR` nos ambientes (padrão da imagem, dev por montagem de `ml/notebooks`, stack por `/opt/airflow/git/current/ml/notebooks`); verificar no compose de dev que a DAG acha o notebook montado do disco
- [ ] 3.5 Atualizar `airflow/README.md` e a docstring da DAG (tarefas rodam o notebook; arquivo por execução; sem `atlas-ml forecast`); verificar que o texto bate com a DAG carregada

## 4. Remoção do CLI de previsão

- [x] 4.1 Remover o grupo `forecast` de `ml/src/atlas_ml/cli.py` e o módulo `ml/src/atlas_ml/forecast/pipeline.py`; verificar que `uv run atlas-ml forecast prepare` informa comando inexistente, que `atlas-ml promote --help` continua funcionando e que `uv run pytest` fica verde
- [x] 4.2 Atualizar as referências: seção do `ml/README.md`, `ml/src/atlas_ml/models/ensemble/README.md` e a docstring de `forecast/threads.py` se citarem o CLI; verificar com `grep -rn "atlas-ml forecast\|forecast.pipeline"` sem ocorrências fora de `openspec/changes` e de `local/`
- [x] 4.3 Registrar a migração de `local/treino_local.py` (fora do Git) no `ml/README.md`: como rodar o notebook com `papermill` ou chamar `dataset.prepare` e `base.run_model`; verificar executando o exemplo documentado com `painel_parquet`

## 5. Entrega das DAGs por `git-sync`

- [x] 5.1 Adicionar ao `docker-compose.yml` o serviço `git-sync` (imagem com tag fixa, `GITSYNC_REPO`, `GITSYNC_REF`, `GITSYNC_PERIOD`, `GITSYNC_DEPTH=1`, link `current`) e o volume `airflow_dags`, montado somente leitura em scheduler, dag-processor, triggerer e api-server com `AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/git/current/airflow/dags` e `AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL` curto; verificar com `docker stack config` para hml e prod
- [ ] 5.2 Fazer cada serviço do Airflow esperar o link `current` (laço com limite de tempo e mensagem) antes de iniciar; verificar subindo o stack sem clone e vendo a mensagem de espera, e depois com clone
- [x] 5.3 Declarar as variáveis novas em `.env.example` (`ATLAS_DAGS_REPO`, `ATLAS_DAGS_BRANCH` por ambiente, `ATLAS_DAGS_SYNC_PERIOD`, `ATLAS_NOTEBOOKS_DIR`, `ATLAS_PIPELINE_DIR`); verificar que `platform/ci/check-stack.sh` as encontra
- [x] 5.4 Ajustar `platform/ci/check-stack.sh` para aceitar a imagem do `git-sync` (com tag fixa) além das do projeto, `postgres` e `redis`, e manter as demais regras; verificar com `bash platform/ci/check-stack.sh` e com um teste negativo (outra imagem externa falha)
- [ ] 5.5 Trocar `Path(__file__).resolve()` por `Path(__file__).absolute()` em `dbt_brasil.py` e `process_dbt_docs_atlas.py`, para o caminho do projeto dbt ficar estável pelo link simbólico; verificar com `airflow/tests/test_dags.py` e conferindo que o caminho do projeto não muda entre dois commits
- [ ] 5.6 Atualizar `deploy/README.md` (serviço `git-sync`, branches por ambiente, intervalo, falha segura, primeira partida, proteção de branch, repositório privado e secret, reversão); verificar seguindo o texto num `docker stack config`

## 6. CI e publicação da imagem

- [ ] 6.1 Ajustar `paths` de `.github/workflows/airflow.yml`: incluir `airflow/**` e `ml/**`, excluir `airflow/dags/**` e `ml/notebooks/**`, reincluir `airflow/dags/utfpr_dengue/pyproject.toml` e `uv.lock`; verificar com um PR que muda só uma DAG (workflow não roda) e outro que muda `ml/src` (roda)
- [x] 6.2 Manter a cópia de `airflow/dags` e de `ml/notebooks` no `airflow/Dockerfile` só para o CI e como reserva, e comentar o motivo no arquivo; verificar que `ci.yml` continua executando `/opt/atlas/tests/*` na imagem construída

## 7. Jupyter de exploração

- [ ] 7.1 Configurar o alvo `notebook` de `ml/Dockerfile` para o stack (arquivo de configuração do Jupyter: sem terminal, sem root, token lido de arquivo de secret, falha ao subir se o arquivo faltar ou estiver vazio, `root_dir` no volume de trabalho; cópia de `ml/notebooks` para o volume quando vazio) e publicá-lo como `atlas-epidemiologia-ml-notebook` em `ml.yml`, `release.yml` e na lista de imagens do `check-stack.sh`; verificar construindo a imagem e rodando-a: sem o arquivo de token ela não sobe, com ele sobe e a API de terminais recusa
- [ ] 7.2 Ler o experimento de `ATLAS_FORECAST_EXPERIMENT` em `atlas_ml.forecast` (padrão `dengue-forecast-br`), usado por `dataset`, `base`, `compare` e pela leitura do export; verificar com testes: sem a variável as runs vão para `atlas/dengue-forecast-br`; com a variável apontando para o sandbox o experimento oficial não recebe run e a comparação lê o experimento configurado
- [ ] 7.3 Adicionar o serviço `jupyter` ao `docker-compose.yml` (imagem do `ml` notebook com a mesma tag do Airflow, `replicas: ${JUPYTER_REPLICAS:-1}`, secrets próprios `jupyter_sa` e `jupyter_token`, volume `airflow_dags` somente leitura em `/opt/airflow/git` e volume `jupyter_work`, `cap_drop: [ALL]`, `read_only: true` com `tmpfs`, limites de CPU e memória, sem porta publicada, labels do Traefik com o mesmo `ipallowlist` e TLS, `ATLAS_FORECAST_EXPERIMENT` do sandbox, usuário próprio do MLflow); verificar com `docker stack config` para hml e prod e conferindo que `no-new-privileges` não foi usado (não é aceito em Swarm)
- [ ] 7.4 Declarar em `.env.example` as variáveis novas (`JUPYTER_REPLICAS`, `JUPYTER_HOST`, `JUPYTER_MLFLOW_USERNAME`, `JUPYTER_MLFLOW_PASSWORD`, `JUPYTER_BQ_MAX_BYTES` e o experimento sandbox) e acrescentar ao `platform/ci/check-stack.sh` as regras do serviço `jupyter` (sem porta publicada, sem os secrets `training_sa`, `mlflow_sa` e `backend_sa`, com os secrets próprios, com `cap_drop` e `read_only`); verificar com `bash platform/ci/check-stack.sh` e com testes negativos (cada violação falha)
- [ ] 7.5 Documentar em `deploy/README.md` a receita do acesso seguro, por ambiente: conta `atlas-<amb>-jupyter` e seus papéis (`jobUser`, `dataViewer` só em `gold<_amb>` e `forecast<_amb>`, `dataEditor` só em `sandbox_jupyter<_amb>` com expiração), cota diária de bytes, condições IAM por prefixo no bucket (`forecast/<amb>/` leitura e `jupyter/<amb>/` escrita), usuário e permissões no MLflow, criação dos secrets `atlas_<amb>_jupyter_sa` e `atlas_<amb>_jupyter_token`, rotação das chaves e `JUPYTER_REPLICAS=0` para desligar, além dos testes negativos a rodar (bronze, silver e `landing/` negados; escrita na gold negada); verificar que cada comando do texto roda como escrito num ambiente de teste
- [ ] 7.6 Verificar notebooks sem saídas: acrescentar `nbstripout` ao grupo de desenvolvimento de `ml/pyproject.toml`, uma verificação em `ci.yml` (falha apontando o arquivo se `ml/notebooks/*.ipynb` tiver saídas) e ao `.githooks/pre-commit`; verificar com um notebook de teste com saída (o CI falha) e com o `forecast_pipeline.ipynb` (passa)
- [ ] 7.7 Alinhar o Jupyter de dev em `platform/compose.dev.yml`: `JUPYTER_TOKEN` obrigatório (sem o padrão `atlas`), `ml/notebooks` e `airflow/dags` montados como no Airflow de dev, `ATLAS_FORECAST_EXPERIMENT` do sandbox e uma chave de leitura própria (`platform/secrets/jupyter-sa.json`) no lugar de `training-sa.json`; verificar com `docker compose config` e vendo que sem o token o serviço não sobe

## 8. Integração em hml e prod

- [ ] 8.1 Publicar a imagem nova em hml (com papermill) e subir o `git-sync` na branch `hml`; verificar que as DAGs aparecem no Airflow vindas do clone e que o `atlas.notebook_sha` de uma run bate com o commit de `hml`
- [ ] 8.2 Disparar `dbt_brasil` a partir do clone em hml; verificar que o dbt roda com o projeto somente leitura (ou com `DBT_TARGET_PATH`, `DBT_LOG_PATH` e `DBT_PACKAGES_INSTALL_PATH` em `/tmp`) e que o cache do Cosmos não é invalidado por um merge que não toca o projeto
- [ ] 8.3 Disparar `atlas_dengue_forecast_br` em hml com um modelo leve e um horizonte (parâmetros do disparo); verificar as runs com `atlas.pipeline_run`, o notebook executado como artefato, o diretório por execução removido ao final e a exportação disparada
- [ ] 8.4 Testar o merge refletindo: alterar a descrição de uma DAG na branch `hml` e verificar que aparece em até o intervalo de sincronização, sem nova imagem; testar também GitHub inacessível (bloquear a rede do serviço) e ver as DAGs da última versão continuarem
- [ ] 8.5 Repetir a validação em prod (branch `main`) depois de aprovada em hml e registrar os resultados e os tempos em `docs/referencias/resultados-forecast-br.md`; verificar `git log -1 --stat` dos commits do módulo sem chaves ou credenciais
- [ ] 8.6 Validar o Jupyter em hml e, depois, em prod: acesso só pelos IPs permitidos e com o token, mesmas versões do `atlas_ml` que o Airflow (`pip show`/`uv pip list` nos dois), leitura de `gold` e `forecast`, execução do notebook do pipeline com o passo `train` caindo no experimento sandbox, escrita no dataset sandbox e no prefixo `jupyter/<amb>/`; e os testes negativos: bronze, silver e `landing/` negados, escrita na gold negada, registro de modelo negado, terminal recusado e serviço sem o secret do token não sobe; registrar o resultado em `docs/referencias/resultados-forecast-br.md`

## Workflow follow-up

- Aplicar depois que `add-hml-stack` e `add-hml-cicd-images` fecharem, ou combinar a ordem dos merges, porque as três mudanças tocam `docker-compose.yml`, `check-stack.sh`, `airflow.yml` e `deploy/README.md`.
- Ativar proteção das branches `hml` e `main` no GitHub antes de ligar o `git-sync` em hml e prod.
- Criar fora do repositório, antes do primeiro deploy do Jupyter em cada ambiente: a conta de serviço de leitura, o dataset sandbox, as condições IAM do bucket, o usuário do MLflow e os Docker secrets `atlas_<amb>_jupyter_sa` e `atlas_<amb>_jupyter_token` (receita na tarefa 7.5).
- Arquivar a mudança quando hml e prod estiverem lendo as DAGs do clone.
