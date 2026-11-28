# Airflow do Atlas (`atlas-epidemiologia-airflow`)

Airflow 3.3.2 (Python 3.12) com LocalExecutor. Ele dispara os treinos do pacote `atlas_ml`, e depois também a ingestão e o dbt. O pacote fica num venv separado (`/opt/atlas-ml`) e é chamado pelo CLI `atlas-ml`, o mesmo comando usado na sua máquina e na imagem de treino.

## Regra principal: DAG só muda pelo repositório

- As DAGs vivem em `airflow/dags/`. **Nunca edite uma DAG direto no servidor.**
- **Dev:** a pasta é montada no container, e o Airflow local relê os arquivos em cerca de 30 s, sem rebuild.
- **hml e prod:** as DAGs e os notebooks chegam pelo **git-sync** (clone da branch do ambiente, `hml` ou `main`, relido a cada 60 s), sem imagem nova. Uma DAG nova chega a hml quando o PR `dev` → `hml` é mesclado. A imagem só é reconstruída quando mudam o pacote `atlas_ml`, os venvs, o Dockerfile ou a configuração.

## Como adicionar ou mudar uma DAG

1. Crie ou edite `airflow/dags/<nome>.py`. Use `from airflow.sdk import DAG` e os operadores de `airflow.providers.standard`.
   - Tarefas de ML usam `@task.external_python` no venv `/opt/atlas-ml/bin/python`, com o corpo autocontido. Não importe `atlas_ml` no topo da DAG: ele vive em outro venv.
   - Código comum entre DAGs fica em `airflow/dags/atlas_ingest/`. O Airflow põe a pasta das DAGs no `sys.path`, então `from atlas_ingest... import ...` funciona no topo do arquivo.
   - Prefira `schedule=None` até a DAG estar validada. As DAGs nascem pausadas (as de modelo de previsão são a exceção).
2. Se a DAG tiver regras importantes (agendamento, retentativas, pools, regras de disparo), acrescente uma função `test_*` em `airflow/tests/test_dags.py`.
3. Rode os testes das DAGs, sem banco e sem subir o Airflow. São os mesmos do job `dags` do CI e levam menos de 1 minuto:
   ```sh
   bash platform/ci/testar-dags.sh               # imagem local atlas-epidemiologia-airflow:local
   bash platform/ci/testar-dags.sh --publicada   # imagem :hml do DockerHub (a da via rápida do CI)
   bash platform/ci/testar-dags.sh test_dags.py  # só um arquivo
   ```
   O script monta as DAGs, os testes e os notebooks do disco sobre a imagem: uma imagem local de dias atrás serve, desde que as dependências não tenham mudado.
4. Teste no Airflow local (`platform/compose.dev.yml`): despause e dispare pela UI em <http://127.0.0.1:8080>.
5. Faça um commit em `dev` ao concluir o módulo e abra o PR para `hml`. Um PR que muda só DAGs (e os testes delas), notebooks, docs ou OpenSpec roda o CI na **via rápida**, em poucos minutos (ver `deploy/README.md`).

## Configuração

| Onde | O quê |
|---|---|
| `Dockerfile` (comum) | `LocalExecutor`, `parallelism=4`, sem DAGs de exemplo, DAGs pausadas ao criar |
| `config/dev.env` | `ATLAS_ENV=dev`, Simple Auth Manager (usuário `admin`), releitura rápida das DAGs |
| `config/vps.env` | FAB Auth Manager (login e senha), sem expor a configuração na API |
| Variáveis da stack (Portainer) | `ATLAS_ENV` (`hml`/`prod`), conexão do banco, chaves do Airflow, `MLFLOW_TRACKING_URI` e credenciais do MLflow |
| `config/init.sh` | Serviço `airflow-init`: `airflow db migrate` + admin (FAB) ou arquivo de senha (Simple). É idempotente |

As tarefas herdam o ambiente do container (`MLFLOW_TRACKING_URI`, `ATLAS_ENV`, `ATLAS_IMAGE_TAG`, `MLFLOW_TRACKING_USERNAME`/`PASSWORD`). Por isso as runs aparecem no MLflow com `atlas.env` e `atlas.image_tag` do ambiente certo.

## DAGs atuais

| DAG | Agendamento | O que faz |
|---|---|---|
| `etl_brasil` | **diária, 03h00 de Brasília** (hml e prod; em dev, manual) | Orquestra o fluxo do Brasil: dispara e espera, em sequência, `ingestao_sinan_brasil`, `dbt_brasil` e o treino (`atlas_dengue_forecast_br`, base inteira). O dbt e o treino só rodam com dados novos. Parâmetros `forcar_dbt` e `forcar_treino` |
| `ingestao_sinan_brasil` | disparada (ou manual) | Sync do SINAN: OpenDataSUS → landing no bucket → tabela bronze. Parâmetro `janela_horas` (0 = verifica uma vez; a `etl_brasil` usa 3) |
| `dbt_brasil` | disparada (ou manual) | Modelagem dbt pelo **Cosmos**, `seed → bronze → silver → gold`, uma tarefa por model com os testes logo depois, só se a bronze do SINAN for mais nova que a gold (ou com `forcar_dbt`) |
| `process_dbt_docs_atlas` | manual | Gera o dbt docs (`index.html`, `manifest.json`, `catalog.json`) e publica em `gs://ppgcc-bucket/dbt_docs/<ATLAS_ENV>/`; o Airflow mostra no menu de dbt docs |
| `atlas_dengue_forecast_br` | disparada pela `etl_brasil` (ou manual) | **Orquestrador** da previsão de dengue por UF em 4 horizontes: `iniciar_execucao → 5 DAGs de modelo-base (baseline bayesiano, Chronos, CatBoost, SVR, LSTM) → DAG do ensemble → comparar por horizonte → exportar`. Fixa a versão da gold e a dos notebooks e dispara cada DAG de modelo individualmente, esperando no triggerer (sem vaga de worker). A comparação é código desta DAG, e a exportação só é disparada se algum horizonte teve modelo. Parâmetros opcionais `window`, `horizons`, `seed` e `fonte` (vazio = gold completa). Detalhes em [DAGs de previsão](#dags-de-previsão-uma-por-modelo) |
| `atlas_forecast_<modelo>` (seis) | disparada pelo orquestrador (ou manual) | Treina **um** modelo (`baseline_bayes`, `chronos`, `catboost`, `svr`, `lstm` ou `ensemble`) nos horizontes pedidos e registra no MLflow como `atlas-br-<modelo>-h<H>`. Sozinha, não compara nem exporta. Nasce despausada |

### etl_brasil (fluxo diário do Brasil)

```
ingestao_sinan ─► modelagem_dbt ─► decidir_treino ─► treino_previsao
(ingestao_sinan_brasil) (dbt_brasil)   (gold mudou?)    (atlas_dengue_forecast_br, base inteira → exportação)
```

- **Agendamento:** todo dia às 03h00 de Brasília em hml e prod (`ATLAS_ENV`); em dev não há agendamento. Sem catchup, uma execução por vez.
- **Sequência:** cada etapa é uma DAG própria; a seguinte só começa quando a anterior termina com sucesso. A espera fica no triggerer e não ocupa vaga de execução.
- **Só com dados novos**, decidido pelo estado das tabelas (uma etapa que falhou ontem é retomada hoje):
  - dbt: se `bronze.sinan_dengue_opendatasus` foi modificada depois de `gold.gold_dengue_casos_provaveis_uf_semanal`;
  - treino: se a versão atual da gold não é a `atlas.data_version` dos 24 modelos vigentes (alias do ambiente) no MLflow, ou se falta algum.
- **Forçar:** dispare a `etl_brasil` com `{"forcar_dbt": true}` ou `{"forcar_treino": true}`; ou dispare cada DAG sozinha.
- **Falha:** as etapas seguintes não rodam e a `etl_brasil` fica com falha; o site continua com a gold e as previsões anteriores.
- **Recursos (VPS de hml):** pool `atlas_treino` com 2 vagas (criado pelo `init.sh`; LSTM, Bayesiano e Chronos ocupam as duas), `ATLAS_THREADS=2`, scheduler limitado a 3 CPUs e 3,5 GB no stack.

### ingestao_sinan_brasil e dbt_brasil (sync do SINAN + Cosmos)

```
ingestao_sinan_brasil: detectar_diferencas (sensor) ─► baixar/apagar[arquivo] ─► carregar_bronze/validar/marcar_carregado[ano]
                       remover_da_bronze[ano] ─► resumo
dbt_brasil:            decidir_dbt ─► [seed] ─► [bronze] ─► [silver] ─► [gold]
```

- **Sensor:** com `janela_horas` > 0 (a `etl_brasil` usa 3), espera até haver diferença entre o OpenDataSUS e o landing, conferindo a cada 30 min, sem ocupar o worker entre as checagens. Sem diferença na janela, termina "sem dados novos". Disparada à mão (`janela_horas` 0), verifica uma vez.
- **Sync do SINAN (espelho exato):**
  - o sensor compara `ETag`/`Last-Modified` dos arquivos `DENGBR<aa>.csv.zip` com a metadata dos objetos em `gs://ppgcc-bucket/landing/sinan/dengue/`;
  - arquivo novo ou alterado é baixado (zip original + CSV) e substitui o anterior; arquivo que sumiu da origem é apagado do landing e o ano sai da bronze.
- **Tabela bronze:** `bronze.sinan_dengue_opendatasus`, uma partição por ano, substituída inteira, com as colunas de origem como texto e as de linhagem (`ano_arquivo`, `arquivo_etag`, `arquivo_uri`, `carregado_em`).
  - Depois de validar as contagens e as colunas obrigatórias, o ano é marcado com `bronze_etag` na metadata do zip.
  - Ano que falhou volta no dia seguinte, sem baixar de novo.
- **Estado:** fica na metadata dos objetos do landing (`origem_etag`, `origem_last_modified`, `registros`, `colunas`, `encoding`, `bronze_etag`). Não há tabela de controle.
- **Forçar a recarga de um ano:** apague o `bronze_etag` do zip (recarrega só a bronze) ou o próprio objeto `DENGBR<aa>.csv.zip` (baixa de novo).
- **dbt:**
  - `decidir_dbt` roda os grupos só se a bronze do SINAN for mais nova que a gold;
  - num disparo manual, `{"forcar_dbt": true}` roda o dbt mesmo sem dados novos (ex.: mudança só na modelagem);
  - para refazer só parte, limpe (Clear) a tarefa de um model ou um grupo inteiro (ex.: `gold`).
- **Grafo:** o Cosmos monta as tarefas com `dbt ls` na leitura da DAG e guarda o resultado em cache. Um model novo em `models/<camada>/` aparece sozinho no grupo da camada. A primeira leitura leva alguns segundos (`AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT=120`).
- **Falhas:** a tarefa do model que falhou fica vermelha, com o erro do dbt no log, e as dependentes ficam `upstream_failed`.
- **Execução:** cada tarefa roda o dbt de `/opt/dbt` numa cópia temporária do projeto. Nada é escrito na pasta de DAGs.
- **Credencial:** `DBT_BQ_KEYFILE`; em dev, `/secrets/training-sa.json`; em hml/prod, o Docker secret montado como `/run/secrets/training_sa.json` (com extensão: o provider do Google recusa sem).
- **Custo:** o build completo processa cerca de 9 GiB no BigQuery ([detalhes](dags/utfpr_dengue/README.md#custo-e-tempo-do-build-completo)).
- **Pasta de DAGs:** o projeto dbt fica dentro dela e é ignorado pelo processador de DAGs (`dags/.airflowignore`).

### process_dbt_docs_atlas e o menu de dbt docs

- **Geração:** a DAG roda `dbt docs generate` (consulta o BigQuery para o catálogo) e envia os arquivos para `gs://<ATLAS_DBT_DOCS_BUCKET>/dbt_docs/<ATLAS_ENV>/`. O bucket padrão é `ppgcc-bucket`.
- **Visualização:** o plugin do Cosmos mostra a documentação no menu do Airflow, configurado por:
  ```
  AIRFLOW__COSMOS__DBT_DOCS_PROJECTS='{"atlas": {"dir": "gs://ppgcc-bucket/dbt_docs/<ambiente>", "conn_id": "google_cloud_default", "index": "index.html", "name": "dbt Docs (Atlas)"}}'
  ```
- **Credencial:** bucket e plugin usam a Connection `google_cloud_default`.
  - Em dev, ela vem por variável de ambiente com o caminho da chave montada (`key_path`), sem o conteúdo.
  - Em hml/prod, cadastre pela UI (Admin → Connections, tipo Google Cloud, campo Keyfile JSON) e ajuste o sufixo do `DBT_DOCS_PROJECTS` na stack.

### DAGs de previsão (uma por modelo)

Cada modelo treina na própria DAG, `atlas_forecast_<modelo>`, montada por `dags/atlas_ingest/forecast_modelo.py` (um arquivo `dags/atlas_forecast_<modelo>.py` por modelo, que só chama a fábrica). O orquestrador `atlas_dengue_forecast_br` dispara as seis no processo completo.

```
atlas_dengue_forecast_br (orquestrador)
  configuracao → lista_de_horizontes → iniciar_execucao → conf_dos_modelos
    → modelo_baseline_bayes, modelo_chronos, modelo_catboost, modelo_svr, modelo_lstm (em paralelo)
    → modelo_ensemble (depois das cinco, com sucesso ou falha)
    → comparar[h] (all_done) → algum_resultado → exportar (process_forecast_export_atlas)

atlas_forecast_<modelo>
  configuracao → lista_de_horizontes → iniciar
    → horizonte[h]: [bases →] treinar        (um grupo por horizonte; um que falha não para os outros)
    → concluir (falha se algum horizonte falhou) e limpar (sempre)
```

- **Treino:** cada `horizonte.treinar` executa o notebook do modelo (`ml/notebooks/<modelo>/<modelo>.ipynb`, papermill, lido de `ATLAS_NOTEBOOKS_DIR`), no pool `atlas_treino`: LSTM, bayesiano e Chronos ocupam as 2 vagas (um pesado por vez), os demais 1, até 3 h por treino. Os arquivos ficam em `ATLAS_PIPELINE_DIR/<pipeline_run>/<modelo>/` (padrão `/tmp/atlas`), e o notebook executado vira artefato da run.
- **Parâmetros (todos opcionais):** `horizons` (1 a 4, padrão todos), `window` (12), `seed` (42), `fonte` (vazio = gold do ambiente) e, preenchidos pelo orquestrador, `pipeline_run`, `data_version` e `notebook_sha`.
- **Disparo pelo orquestrador:** run `<run_id do orquestrador>__<modelo>`, com a conf da execução. Todas as runs do MLflow levam o mesmo `atlas.pipeline_run`, e os notebooks falham se a gold ou o notebook mudarem no meio.
- **Disparo isolado (à mão):** treina e registra, **sem comparar nem exportar**. O `pipeline_run` é o `run_id` da própria DAG, e as versões são as atuais. Serve para repetir ou depurar um modelo; por exemplo, o SVR só no horizonte 1:
  ```json
  {"horizons": [1]}
  ```
- **Ensemble:** a tarefa `horizonte.bases` busca no MLflow as runs concluídas de CatBoost, SVR e LSTM daquele horizonte: as do mesmo `pipeline_run` quando vem do orquestrador; sozinha, as mais recentes com a mesma versão da gold. Se faltar alguma, o horizonte falha dizendo qual modelo treinar antes.
- **Despausadas ao nascer:** as seis nascem despausadas (`is_paused_upon_creation=False`), porque o orquestrador esperaria até 8 h por uma run parada na fila. **Não as pause.**
- **Logs:** `iniciar` mostra as versões (recebidas ou lidas agora) e o notebook; `horizonte.treinar[h]` mostra os parâmetros, a duração, as métricas de teste, a run e a versão registrada; `horizonte.bases[h]` mostra as runs escolhidas, com janela e semente.
