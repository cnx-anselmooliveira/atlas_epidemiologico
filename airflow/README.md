# Airflow do Atlas (`atlas-epidemiologia-airflow`)

Airflow 3.3.2 (Python 3.12) com LocalExecutor. Ele dispara os treinos do pacote `atlas_ml`, e depois também a ingestão e o dbt. O pacote fica num venv separado (`/opt/atlas-ml`) e é chamado pelo CLI `atlas-ml`, o mesmo comando usado na sua máquina e na imagem de treino.

## Regra principal: DAG só muda pelo repositório

- As DAGs vivem em `airflow/dags/`. **Nunca edite uma DAG direto no servidor.**
- **Dev:** a pasta é montada no container, e o Airflow local relê os arquivos em cerca de 30 s, sem rebuild.
- **hml e prod:** as DAGs vão **dentro da imagem**. Uma DAG nova só chega a hml quando o commit é promovido para a branch `hml` e a imagem `:hml` é publicada e implantada. Para prod, o caminho é `main` + tag `vX.Y`.

## Como adicionar uma DAG

1. Crie `airflow/dags/<nome>.py`. Use `from airflow.sdk import DAG` e os operadores de `airflow.providers.standard`.
   - Tarefas de ML chamam o CLI (`BashOperator` com `atlas-ml …`). Não importe `atlas_ml` dentro da DAG: ele vive em outro venv.
   - Prefira `schedule=None` até a DAG estar validada. As DAGs nascem pausadas.
2. Valide a integridade, sem banco e sem subir o Airflow:
   ```sh
   docker build -f airflow/Dockerfile -t atlas-epidemiologia-airflow:local --build-arg ATLAS_GIT_SHA=$(git rev-parse HEAD) .
   docker run --rm -v "$PWD/airflow/dags:/opt/airflow/dags" --entrypoint python \
     atlas-epidemiologia-airflow:local /opt/atlas/tests/test_dags.py
   ```
   No Git Bash do Windows, prefixe o comando com `MSYS_NO_PATHCONV=1`.
3. Se a DAG tiver regras importantes (agendamento, retentativas, comando), acrescente uma função `test_*` em `airflow/tests/test_dags.py`.
4. Teste no Airflow local (`platform/compose.dev.yml`): despause e dispare pela UI em <http://127.0.0.1:8080>.
5. Faça um commit em `dev` ao concluir o módulo. A promoção segue `dev → hml → main`.

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
| `atlas_dengue_forecast_br` | disparada pela `etl_brasil` (ou manual) | Previsão de dengue por UF em 4 horizontes: `iniciar_execucao → 5 modelos-base (baseline bayesiano, Chronos, CatBoost, SVR, LSTM) → ensemble → compare → exportar`, com `limpar` no fim. Cada tarefa de modelo **executa o notebook do modelo** (`ml/notebooks/<modelo>/<modelo>.ipynb`, papermill, lido de `ATLAS_NOTEBOOKS_DIR`), que lê a gold direto; a `iniciar_execucao` registra a versão da gold e a do notebook, e os notebooks falham se mudarem no meio; a comparação é código da própria DAG; os arquivos de cada execução ficam em `ATLAS_PIPELINE_DIR/<run_id>/` (padrão `/tmp/atlas`) e o notebook executado vira artefato da run. Treinos no pool `atlas_treino` (um pesado por vez), no máximo 2 tarefas em paralelo, até 3 h por treino. Parâmetros opcionais `window`, `horizons`, `seed` e `fonte` (vazio = gold completa). Modelos registrados como `atlas-br-<modelo>-h<H>` |

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
