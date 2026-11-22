# Proposal

## Why

Hoje o pipeline de previsão só pode ser executado de duas formas: pelas funções de `atlas_ml.forecast.pipeline`, que a DAG chama, ou pelo CLI `atlas-ml forecast …`, que repete a mesma orquestração em outro lugar. Quem quer inspecionar um passo, trocar um parâmetro ou ver a saída intermediária precisa editar Python dentro da imagem. Além disso, as DAGs viajam dentro da imagem do Airflow: um ajuste numa DAG exige build, publicação e redeploy da imagem (pesada, por causa de torch, PyMC e CatBoost), em vez de um simples merge.

Queremos que o pipeline seja um notebook revisável em PR, que o Airflow o execute com parâmetros e que o merge de uma DAG reflita no Airflow sem reconstruir a imagem.

## What Changes

- **Notebook como pipeline.** Um notebook parametrizado em `ml/notebooks/` passa a ser a orquestração do pipeline de previsão (snapshot, treino de um modelo num horizonte, comparação). As células são finas e chamam o pacote `atlas_ml`, que continua com o código de dados, janelas, modelos e avaliação e com seus testes `pytest`.
- **Airflow executa o notebook.** As tarefas da DAG `atlas_dengue_forecast_br` passam a rodar o notebook (papermill, no venv do `atlas_ml`) com os parâmetros da tarefa. A forma da DAG (ordem, pool `atlas_treino`, 4 horizontes, `trigger_rule`) não muda.
- **Saída por arquivo, quando preciso.** O notebook continua registrando no MLflow. Quando precisar entregar uma tabela ou muitos parâmetros, grava um arquivo num diretório por execução (padrão `/tmp/atlas/<run_id>/`); uma tarefa seguinte do Airflow o lê e o escreve no MLflow ou no BigQuery. O notebook executado fica guardado como artefato da run.
- **Fim do CLI de previsão. BREAKING.** Saem o grupo `atlas-ml forecast` (`prepare`, `train`, `compare`) e o módulo `forecast/pipeline.py`. O restante do CLI (`train example`, `promote` etc.) fica. Quem usa as funções fora do Git (`local/treino_local.py`) precisa migrar para o notebook.
- **DAGs vindas do GitHub.** Um serviço `git-sync` no stack clona o repositório num volume lido pelo Airflow: hml pela branch `hml`, prod pela `main`. Fazer o merge na branch do ambiente atualiza as DAGs e o notebook, sem rebuild. O dbt/Cosmos continua em `airflow/dags/utfpr_dengue`, agora lido do clone. A imagem segue com os venvs (`atlas_ml`, dbt) e o pacote `atlas_ml`.
- **CI e imagem.** O gatilho de build da imagem do Airflow deixa de reagir a mudanças só de DAG ou de notebook; `check-stack.sh` passa a aceitar a imagem do `git-sync`; as dependências de execução de notebook entram no venv do `atlas_ml`.
- **Jupyter de exploração.** Um serviço `jupyter` no stack (dev, hml e prod) para testar e explorar os dados com uma cópia do que o Airflow roda: a imagem `ml` com o alvo `notebook` (mesmo `ml/uv.lock` e mesmo commit, portanto as mesmas versões do `atlas_ml`) e o clone do `git-sync` em somente leitura. O acesso aos dados é de leitura e por uma conta de serviço própria: BigQuery só em `gold` e `forecast` do ambiente (sem bronze nem silver) e bucket só nos prefixos `forecast/<ambiente>/` (leitura) e `jupyter/<ambiente>/` (escrita), sem o SINAN bruto. A escrita vai para um dataset sandbox com expiração e para um experimento sandbox do MLflow. O acesso ao serviço é restrito (allowlist de IPs no Traefik, TLS, token em Docker secret, sem terminal) e o contêiner roda sem privilégios, com limites de recursos.
- Fora de escopo: trocar o executor do Airflow, mudar modelos, features ou o contrato do export para o BigQuery, e o Airflow de dev (que já monta `airflow/dags` do disco, ao vivo).

## Capabilities

### New Capabilities
- `forecast-notebook-pipeline`: execução do pipeline de previsão por notebook parametrizado, chamado pelo Airflow, com troca de arquivos por execução, notebook executado como artefato e sem CLI de previsão.
- `airflow-dag-delivery`: entrega das DAGs e do notebook ao Airflow por clone do GitHub (`git-sync`), por branch e ambiente, com falha segura e sem rebuild da imagem.
- `jupyter-exploration-service`: serviço Jupyter de exploração por ambiente, com as mesmas versões e o mesmo clone do Airflow, acesso de leitura por conta própria a BigQuery e bucket, escrita só em sandbox e acesso restrito.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/ (ainda não há specs arquivadas). A DAG `atlas_dengue_forecast_br` da mudança `add-dengue-forecast-models` (spec forecast-training-dag) mantém seus requisitos; só muda como as tarefas executam. -->

## Impact

- **Código**:
  - novo `ml/notebooks/forecast_pipeline.ipynb` e testes que o executam num painel sintético;
  - `ml/src/atlas_ml/cli.py` perde o grupo `forecast`; `ml/src/atlas_ml/forecast/pipeline.py` é removido;
  - `airflow/dags/atlas_dengue_forecast_br.py` troca as chamadas a `pipeline` pela execução do notebook e ganha a tarefa de ingestão do arquivo;
  - `airflow/dags/process_forecast_export_atlas.py` pode reaproveitar o arquivo por execução, a decidir no design.
- **Dependências e imagem**: `papermill` e um kernel Jupyter no venv do `atlas_ml` (`ml/pyproject.toml`, `uv.lock`); `airflow/Dockerfile` deixa de ser a fonte das DAGs em hml e prod (continua copiando para o CI e como reserva).
- **Stack (hml e prod)**: serviço `git-sync` e volume novo, montado em scheduler, dag-processor, triggerer e api-server; variáveis de branch e repositório; `docker-compose.yml`, `.env.example`, `platform/ci/check-stack.sh` e `deploy/README.md`.
- **CI**: `.github/workflows/airflow.yml` (filtros de caminho); `ci.yml` continua testando as DAGs na imagem e passa a verificar que os notebooks versionados não têm saídas (`nbstripout`).
- **Jupyter de exploração**: o alvo `notebook` de `ml/Dockerfile` passa a ser publicado (hoje não é; `ml.yml`, `release.yml` e a seção de imagens do `deploy/README.md`); serviço `jupyter` e volume de trabalho no `docker-compose.yml`; regras novas no `check-stack.sh`; `ATLAS_FORECAST_EXPERIMENT` no `atlas_ml`; `compose.dev.yml` (token obrigatório).
- **GCP e MLflow (fora do repositório)**: uma conta de serviço de leitura por ambiente com papéis por dataset e por prefixo, um dataset sandbox com expiração, um usuário do MLflow com permissões mínimas e dois Docker secrets por ambiente (`atlas_<ambiente>_jupyter_sa` e `atlas_<ambiente>_jupyter_token`).
- **Rede e credenciais**: o repositório é público, então o `git-sync` lê por HTTPS sem credencial; se ele virar privado, será preciso um secret de deploy key.
- **Sobreposição**: reabre pontos de `add-hml-stack` e `add-hml-cicd-images` (DAGs embutidas na imagem e gatilhos de build), que ainda estão em andamento; o design diz o que muda em cada uma.
