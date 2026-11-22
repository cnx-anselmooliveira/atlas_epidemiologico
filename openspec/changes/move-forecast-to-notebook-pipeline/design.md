# Design

## Context

Motivação e escopo: ver `proposal.md`. Estado atual relevante:

- **Orquestração duplicada.** `ml/src/atlas_ml/forecast/pipeline.py` (`prepare_snapshot`, `train`, `compare_horizon`) é chamado pela DAG e pelo CLI `atlas-ml forecast …` (`cli.py`, três comandos). Um script pessoal fora do Git (`local/treino_local.py`) também importa `pipeline`.
- **DAG.** `airflow/dags/atlas_dengue_forecast_br.py` usa `@task.external_python` no venv `/opt/atlas-ml`, com o pool `atlas_treino`, 4 horizontes, `trigger_rule` e a tag `atlas.pipeline_run = {{ run_id }}`. Dispara `process_forecast_export_atlas` no fim; o `etl_brasil` dispara a previsão quando a gold muda.
- **DAGs na imagem.** `airflow/Dockerfile` faz `COPY airflow/dags /opt/airflow/dags`, e `.github/workflows/airflow.yml` reconstrói a imagem a cada mudança em `airflow/**` ou `ml/**`. O dev monta `../airflow/dags` do disco (`platform/compose.dev.yml`).
- **Executor.** `LocalExecutor` dentro do scheduler (`replicas: 1`): todas as tarefas rodam no mesmo contêiner. O scheduler tem 3,5 GB e `parallelism` 6.
- **Volume compartilhado já existente.** `airflow_shared` (`/opt/airflow/shared`), usado pela DAG de exportação para trocar arquivos entre tarefas.
- **Imagens do stack.** `platform/ci/check-stack.sh` aceita só imagens do projeto, `postgres` e `redis`.
- **dbt/Cosmos.** `dbt_brasil.py` e `process_dbt_docs_atlas.py` localizam o projeto com `Path(__file__).resolve().parent / "utfpr_dengue"`. O venv do dbt é montado na imagem a partir do `pyproject.toml` e do `uv.lock` desse projeto.
- **Repositório.** `cnx-anselmooliveira/atlas_epidemiologico`, **público**.

## Goals / Non-Goals

**Goals:**
- O pipeline de previsão existe em um só lugar, o notebook, e o que o Airflow executa é exatamente esse notebook.
- Merge na branch do ambiente atualiza DAGs e notebook sem rebuild da imagem.
- Cada run diz que versão do pacote e do notebook a gerou.

**Non-Goals:**
- Mover código de dados, janelas, modelos ou avaliação para o notebook.
- Mudar o executor, a forma da DAG, o contrato do export para o BigQuery ou o treino local em si.
- Versionar DAGs no estilo `GitDagBundle` do Airflow (exigiria o provider git e conexões; ver decisão 4).

## Decisions

### 1. Um notebook, três passos
`ml/notebooks/forecast_pipeline.ipynb` tem uma célula de parâmetros (tag `parameters`) com `step` (`prepare`, `train`, `compare`), `model`, `horizon`, `window`, `seed`, `dataset_run`, `base_runs`, `pipeline_run`, `fonte`, `painel_parquet` e `out_dir`. As células são finas e chamam o pacote:

| Passo | Chama | Resultado (`<nome do passo>.result.json`, um por tarefa) |
|---|---|---|
| `prepare` | `forecast.dataset.prepare` | `dataset_run_id` |
| `train` | `forecast.base.run_model` com `models.get_factory` | `run_id`, métricas de teste, `model_version` |
| `compare` | `forecast.compare.compare` | `run_id` |

`painel_parquet` (opcional) faz o `prepare` gravar o snapshot a partir de um parquet em vez de ler o BigQuery; serve ao teste de CI e a reprocessamentos. Um passo ou modelo desconhecido falha logo na primeira célula, listando os valores aceitos.

*Alternativa descartada:* um notebook por passo. Triplica os artefatos e a manutenção, e não há lógica que justifique separá-los.

### 2. Executar o notebook: papermill no venv do `atlas_ml`
- `papermill` e `ipykernel` entram no venv `/opt/atlas-ml` (grupo `models` de `ml/pyproject.toml`; `uv.lock` atualizado). Rodando o papermill desse Python, o kernel `python3` resolvido é o do próprio venv.
- A tarefa continua `@task.external_python` (mesmo venv, mesmo pool e timeouts). Ela chama `papermill.execute_notebook(...)`, com `log_output=False` e sem barra de progresso, grava o notebook executado em `out_dir` e lê `result.json`.
- Depois do notebook, a **mesma tarefa** anexa o notebook executado à run indicada em `result.json` (`mlflow.MlflowClient().log_artifact`). Isso precisa vir depois porque o notebook só existe pronto ao fim da execução.
- Sem o arquivo de resultado do passo, a tarefa falha. A mensagem aponta o arquivo esperado. Cada tarefa grava o seu (`<nome>.result.json`, por exemplo `train-catboost-h2.result.json`), porque várias tarefas de treino rodam em paralelo no mesmo diretório da execução.

### 3. Arquivos entre tarefas
- Base `ATLAS_PIPELINE_DIR` (padrão `/tmp/atlas`), diretório `<base>/<run_id normalizado>/`, criado pela tarefa `configuracao` e removido por uma tarefa final `limpar` (`trigger_rule="all_done"`).
- O arquivo de resultado do passo (`<nome>.result.json`) é obrigatório em todos os passos. Tabelas e parâmetros extensos são opcionais: o notebook grava parquet ou JSON no mesmo diretório e uma tarefa seguinte os lê e escreve no MLflow ou no BigQuery. Hoje nenhum passo entrega tabela além do resultado; o mecanismo (diretório, leitura, limpeza e ingestão idempotente) é implementado e testado, e o primeiro uso real fica para quando algum passo precisar.
- `/tmp` do contêiner é efêmero: um reinício do scheduler no meio da execução perde os arquivos. A tarefa seguinte falha com mensagem clara e o disparo é refeito. Como só o resultado é crítico e ele também segue por XCom, o impacto é pequeno. Se virar problema, basta apontar `ATLAS_PIPELINE_DIR` para `/opt/airflow/shared`, o volume que a exportação já usa.
- A ingestão é idempotente pelo identificador da run (a mesma chave da exportação atual): repetir a tarefa regrava as mesmas linhas.

*Alternativa descartada:* só XCom. O XCom guarda no banco do Airflow e não serve para tabelas.

### 4. DAGs do GitHub: `git-sync` como serviço do stack
O Swarm não tem sidecar, então o `git-sync` é um serviço próprio do stack:

- **Imagem:** `registry.k8s.io/git-sync/git-sync`, com tag de versão fixa (nunca `latest`). Exige ajustar `platform/ci/check-stack.sh` para aceitar essa imagem além das do projeto, `postgres` e `redis`.
- **Configuração por variável:** repositório e branch (`GITSYNC_REPO`, `GITSYNC_REF`: `hml` em hml e `main` em prod), `GITSYNC_PERIOD` (padrão 60 s, em `ATLAS_DAGS_SYNC_PERIOD`) e `GITSYNC_DEPTH=1`. HTTPS sem credencial, porque o repositório é público; se for privado, um secret do stack com a credencial.
- **Volume:** `airflow_dags` (nomeado), gravado pelo `git-sync` e montado **somente leitura** em scheduler, dag-processor, triggerer e api-server. O `git-sync` mantém um link simbólico (`current`) que aponta para a árvore da versão e o troca de forma atômica. Isso cumpre a atualização atômica da spec.
- **Variáveis do Airflow:** `AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/git/current/airflow/dags` e `AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL` curto (60 s), para a DAG nova aparecer logo depois da sincronização.
- **Espera pelo primeiro clone:** o Swarm não tem `depends_on`, então o comando de cada serviço do Airflow espera, em laço com limite, o caminho `current` existir antes de iniciar.
- **Notebook:** lido do mesmo clone, por `ATLAS_NOTEBOOKS_DIR` (stack: `/opt/airflow/git/current/ml/notebooks`). No dev, a pasta `ml/notebooks` é montada do disco, como já acontece com as DAGs. A imagem leva uma cópia dos notebooks só para o CI e como padrão quando a variável não existe.
- **O que continua na imagem:** os venvs (`atlas_ml` e dbt), o pacote `atlas_ml`, o `Cosmos` e os testes. A cópia de `airflow/dags` na imagem permanece, mas só para o CI e como reserva: em hml e prod, quem manda é `DAGS_FOLDER`.

*Alternativa descartada:* `GitDagBundle` do Airflow 3. Resolve a entrega, mas exige o provider git, uma conexão e a troca da configuração de bundles, e o usuário preferiu o `git-sync`. Ele também só traria versionamento de DAG se o bundle fosse versionado, o que não resolve a questão do notebook (decisão 6).

### 5. dbt e Cosmos a partir do clone
- `DBT_DIR = Path(__file__).resolve().parent / "utfpr_dengue"` segue o link simbólico até a árvore real, cujo nome muda a cada commit. Isso invalidaria o cache do Cosmos a cada merge (um `dbt ls` de ~60 s). Troca-se `resolve()` por `absolute()` nos dois arquivos, para o caminho ficar estável (`…/current/airflow/dags/utfpr_dengue`); o cache continua valendo pelo conteúdo e só invalida quando o projeto muda.
- O clone é somente leitura. O dbt grava `target/`, `logs/` e `dbt_packages/`. Antes de confiar, verificar em hml se o Cosmos copia o projeto para um diretório temporário. Se não copiar, apontar `DBT_TARGET_PATH`, `DBT_LOG_PATH` e `DBT_PACKAGES_INSTALL_PATH` para `/tmp`.
- O venv do dbt é construído na imagem a partir do `pyproject.toml` e do `uv.lock` de `utfpr_dengue`: mudanças nesses dois arquivos continuam exigindo rebuild da imagem (ver decisão 7).

### 6. Versões do pacote e do notebook
- **Tags:** além de `atlas.git_sha` (a imagem, onde mora o pacote), cada run grava `atlas.notebook_sha`. O notebook obtém o SHA lendo o destino do link do `git-sync` (a árvore tem o SHA no nome), sem precisar de `git` na imagem do Airflow.
- **Contrato:** `atlas_ml.forecast` expõe `NOTEBOOK_API` (inteiro); o notebook declara a versão que exige e a primeira célula falha, antes de criar qualquer run, se a instalada for menor. Isso cobre o caso de um merge que muda o notebook para usar uma função nova de `ml/src` antes de a imagem ser reconstruída.
- **Merge no meio de uma execução:** o modo `dags-folder` do Airflow não versiona o código das DAGs. A tarefa `configuracao` registra o SHA do notebook no início, e cada tarefa de notebook falha com mensagem clara se o SHA atual for diferente. Assim não se misturam versões numa mesma execução; o disparo é refeito depois do merge.

### 7. CI e publicação da imagem
- `airflow.yml` passa a disparar por `airflow/**` e `ml/**`, **exceto** `airflow/dags/**` e `ml/notebooks/**`, reincluindo `airflow/dags/utfpr_dengue/pyproject.toml` e `uv.lock` (que alimentam o venv do dbt). A ordem dos padrões em `paths` importa: os de exclusão vêm depois, e a reinclusão por último.
- `ci.yml` continua construindo a imagem e testando as DAGs com `/opt/atlas/tests/*`: o que chega ao clone já passou pelo CI.
- `ml/tests` ganha o teste que executa o notebook sobre o painel sintético, com MLflow temporário (um modelo leve, sem rede).
- Proteção de branch em `hml` e `main` passa a ser requisito de segurança: quem faz merge executa código no Airflow.

### 8. Remoção do CLI de previsão e do `pipeline.py`
- Saem `forecast_app` (`prepare`, `train`, `compare`) de `cli.py` e o módulo `forecast/pipeline.py`. O que `pipeline.py` fazia além de repassar chamadas (limitar threads, validar o SHA da imagem, apontar o MLflow) vira células de configuração do notebook, usando `forecast.threads.limitar`, `config.load_settings` e `mlflow.set_tracking_uri`.
- Documentação a atualizar: `ml/README.md` (seção `atlas-ml forecast`), o README do ensemble, `airflow/README.md` e `deploy/README.md`.
- `local/treino_local.py` está fora do Git, então não entra no PR: a migração é manual (usar o notebook com `papermill`, ou chamar `dataset.prepare` e `base.run_model` diretamente).

## Risks / Trade-offs

- **[Merge executa código em produção]** → proteção das branches `hml` e `main`; o CI valida as DAGs antes; `atlas.notebook_sha` registra o que rodou.
- **[Notebook novo com pacote antigo]** → contrato `NOTEBOOK_API` com falha antes de qualquer run.
- **[Merge no meio de uma execução de horas]** → tarefas falham se o SHA do notebook mudou; documentar que merges devem esperar o fim do treino.
- **[Clone somente leitura × dbt]** → verificar em hml; se preciso, redirecionar `target`, `logs` e pacotes para `/tmp`.
- **[Cache do Cosmos invalidado a cada merge]** → caminho estável pelo link simbólico (`absolute()`), em vez de `resolve()`.
- **[GitHub fora do ar]** → o Airflow segue com a última versão sincronizada; o `git-sync` registra a falha em log.
- **[Primeira partida sem clone]** → serviços esperam o link `current` antes de iniciar, com limite de tempo e mensagem.
- **[`/tmp` perde arquivos num reinício do scheduler]** → falha clara; alternativa documentada em `/opt/airflow/shared`.
- **[Imagem do `git-sync` fora da regra do `check-stack.sh`]** → ajuste explícito da regra, com tag fixa.
- **[Duas fontes das DAGs (imagem e clone) divergem]** → a variável `DAGS_FOLDER` decide em hml e prod; a cópia da imagem só serve ao CI.
- **[Notebook executado pesa no MLflow]** → `log_output=False` e sem barras de progresso; o treino imprime pouco.
- **[Sobreposição com `add-hml-stack` e `add-hml-cicd-images`]** → esta mudança altera `docker-compose.yml`, `check-stack.sh`, `airflow.yml` e o `deploy/README.md`, que as duas ainda tocam. Aplicar depois de fecharem ou combinar a ordem dos merges; os artefatos delas não são editados aqui.

## Migration Plan

1. Implementar e testar em dev (notebook, testes, remoção do CLI). O dev não usa o `git-sync`.
2. Publicar a imagem nova (papermill no venv) em hml. É a última vez que a imagem entrega DAGs.
3. Subir o `git-sync` em hml (branch `hml`) e verificar a DAG de previsão e as DAGs do dbt a partir do clone, incluindo uma execução curta da previsão com um modelo leve.
4. Repetir em prod (branch `main`) depois de validado.
5. **Reversão:** retirar `AIRFLOW__CORE__DAGS_FOLDER` do stack. O Airflow volta a ler as DAGs que a imagem ainda carrega (por isso a cópia fica). Restaurar o CLI exigiria reverter o commit de remoção.

## Open Questions

- **Primeiro uso real do arquivo de tabela:** nenhum passo entrega tabela hoje; definir qual será (por exemplo, a comparação por horizonte) quando surgir a necessidade.
- **Intervalo de sincronização:** 60 s é um padrão razoável; ajustar depois de ver o consumo de rede e de processamento do dag-processor.
- **Repositório privado no futuro:** se ocorrer, adicionar o secret de acesso ao `git-sync` e à documentação.
