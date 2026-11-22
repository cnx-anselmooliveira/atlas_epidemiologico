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

## 7. Integração em hml e prod

- [ ] 7.1 Publicar a imagem nova em hml (com papermill) e subir o `git-sync` na branch `hml`; verificar que as DAGs aparecem no Airflow vindas do clone e que o `atlas.notebook_sha` de uma run bate com o commit de `hml`
- [ ] 7.2 Disparar `dbt_brasil` a partir do clone em hml; verificar que o dbt roda com o projeto somente leitura (ou com `DBT_TARGET_PATH`, `DBT_LOG_PATH` e `DBT_PACKAGES_INSTALL_PATH` em `/tmp`) e que o cache do Cosmos não é invalidado por um merge que não toca o projeto
- [ ] 7.3 Disparar `atlas_dengue_forecast_br` em hml com um modelo leve e um horizonte (parâmetros do disparo); verificar as runs com `atlas.pipeline_run`, o notebook executado como artefato, o diretório por execução removido ao final e a exportação disparada
- [ ] 7.4 Testar o merge refletindo: alterar a descrição de uma DAG na branch `hml` e verificar que aparece em até o intervalo de sincronização, sem nova imagem; testar também GitHub inacessível (bloquear a rede do serviço) e ver as DAGs da última versão continuarem
- [ ] 7.5 Repetir a validação em prod (branch `main`) depois de aprovada em hml e registrar os resultados e os tempos em `docs/referencias/resultados-forecast-br.md`; verificar `git log -1 --stat` dos commits do módulo sem chaves ou credenciais

## Workflow follow-up

- Aplicar depois que `add-hml-stack` e `add-hml-cicd-images` fecharem, ou combinar a ordem dos merges, porque as três mudanças tocam `docker-compose.yml`, `check-stack.sh`, `airflow.yml` e `deploy/README.md`.
- Ativar proteção das branches `hml` e `main` no GitHub antes de ligar o `git-sync` em hml e prod.
- Arquivar a mudança quando hml e prod estiverem lendo as DAGs do clone.
- O Jupyter de exploração saiu desta change: está na `add-jupyter-hml` (senha e TLS, sem lista de IPs).
