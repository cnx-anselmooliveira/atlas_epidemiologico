# Design

## Context

Veja proposal.md (Why). Estado observado em 2026-11-28:

- `airflow/dags/atlas_dengue_forecast_br.py` tem tudo numa DAG: `configuracao`, `lista_de_horizontes`, `iniciar_execucao` (pasta da execução, `notebook_sha`, versão da gold, conferência dos notebooks), um task group mapeado por horizonte com `train_<modelo>` (`@task.external_python` no venv `/opt/atlas-ml`, executando `run_model_notebook`) e `comparar`, depois `exportar` (`TriggerDagRunOperator` para `process_forecast_export_atlas`) e `limpar`. O ensemble recebe os `run_id` de CatBoost, SVR e LSTM por XCom (`base_runs`).
- Recursos: pool `atlas_treino` (2 vagas, criado pelo `init.sh`), pesados = LSTM, bayesiano e Chronos (2 vagas), `TEMPO_MAX_TREINO` 3 h, `max_active_tasks=2`, `dagrun_timeout` 12 h.
- Funções `external_python` precisam do decorador literal e de corpo autocontido (o Airflow copia o código da função para o venv).
- A `etl_brasil` dispara `atlas_dengue_forecast_br` com `{"fonte": ""}`; `airflow/tests/test_dags.py` testa a forma atual (grupos `horizonte.*`, pools, regras de disparo).
- Stack de hml e dev têm `airflow-triggerer`. `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True` na imagem.
- CI (`ci.yml`): última execução de PR levou ~8 min (o caminho crítico é `images` → `platform-e2e`, 5 min). `airflow.yml` já ignora `airflow/dags/**` e `ml/notebooks/**`; `ml.yml` roda com qualquer `ml/**` (~20 min), porque o alvo `notebook` copia `ml/notebooks` para semear o Jupyter. As publicações chamam o `ci.yml` por `workflow_call`.
- Incidente de 28/11 em hml: o `airflow-dag-processor` estava numa imagem antiga e serializava a DAG com `prepare`. Isso é corrigido por redeploy com *re-pull*, fora desta mudança, mas é pré-requisito da verificação.

## Goals / Non-Goals

**Goals:**
- Treinar, repetir ou depurar um modelo sem rodar os outros.
- Manter o processo completo com uma chamada (`atlas_dengue_forecast_br`), com o mesmo contrato para a `etl_brasil`.
- PR só de DAG ou notebook com CI de poucos minutos, sem perder a integridade das DAGs.

**Non-Goals:**
- Mudar os notebooks, o registro no MLflow, a exportação ou as decisões da `etl_brasil`.
- Um ambiente de dev na VPS, ou o git-sync de hml seguindo `dev`.
- Paralelizar mais que o pool `atlas_treino` permite.

## Decisions

1. **Fábrica única e um arquivo por modelo.** Um módulo novo (`airflow/dags/atlas_ingest/forecast_modelo.py`) define as tarefas (`external_python` literais, como hoje) e `criar_dag_modelo(modelo)`. Cada `airflow/dags/atlas_forecast_<modelo>.py` só chama a fábrica. Os arquivos citam `airflow` e `DAG` no texto, porque o *safe mode* do DagBag pula arquivos sem essas palavras. Um erro de importação no arquivo de um modelo aparece só nele. Alternativa descartada: as seis DAGs geradas num loop num arquivo só, em que um erro derrubaria as seis e o histórico de parse ficaria misturado.

2. **Forma da DAG de modelo:** `configuracao` (params + `conf`) → `iniciar` (usa `pipeline_run`, versão da gold e `notebook_sha` recebidos ou registra os atuais; pasta `run_dir(pipeline_run)/<modelo>`) → `lista_de_horizontes` → `treinar.expand(horizon=...)` → `limpar` (`all_done`). No ensemble, `bases.expand(horizon=...)` vem antes do treino. Cada horizonte é uma tarefa mapeada independente: um horizonte que falha não para os outros, e a run da DAG termina com falha. `max_active_runs=1`, `max_active_tasks=2`, `dagrun_timeout` de 8 h, pool e tempos por `_recursos(modelo)` como hoje, `is_paused_upon_creation=False`.

3. **O ensemble busca as bases no MLflow, não por XCom.** A tarefa `bases` procura, por horizonte, runs `FINISHED` com `atlas.forecast_model` em CatBoost, SVR e LSTM: pela tag `atlas.pipeline_run` quando ela vem no disparo; senão, a mais recente com `atlas.data_version` igual à versão da gold de partida. É a mesma busca que o `comparar` já faz, e a mesma regra vale com e sem orquestrador. Alternativa descartada: o orquestrador ler os XComs de outras DAGs, que acopla as DAGs e não serve para o disparo isolado.

4. **Orquestrador com `TriggerDagRunOperator` adiável.** `configuracao` → `lista_de_horizontes` → `iniciar_execucao` (versões e conferência dos notebooks, sem pasta própria) → `modelo_<base>` ×5 → `modelo_ensemble` (`all_done`) → `comparar.expand(horizon)` (`all_done`) → `exportar`. Cada disparo usa `trigger_run_id="{{ run_id }}__<modelo>"`, `conf` com `pipeline_run={{ run_id }}`, horizontes, janela, semente, fonte, versão da gold e `notebook_sha`, `wait_for_completion=True`, `deferrable=True` (a espera fica no triggerer, sem vaga de worker), `poke_interval=60`, `failed_states=["failed"]`, `retries=0` e `reset_dag_run=True`, para que limpar a tarefa dispare de novo. A `conf` vem de uma tarefa (`conf_dos_modelos`) passada como XCom ao campo `conf`, e não de templates com `render_template_as_native_obj`: assim listas e inteiros chegam com o tipo certo, e um SHA do notebook só com dígitos e um `e` não vira número.

5. **Exportação só com alguma comparação.** O `comparar` de um horizonte falha quando não há nenhuma run. Uma tarefa curta (`algum_resultado`, `all_done`) olha os resultados mapeados do `comparar` e falha se nenhum terminou com sucesso. O `exportar` depende dela com `all_success`. Assim a exportação roda quando pelo menos um horizonte teve modelo, depois de todas as comparações, e não roda quando nada concluiu.

6. **Via rápida decidida por um script testável.** Um job `escopo` roda `platform/ci/escopo.sh`, que recebe a lista de arquivos alterados (`git diff --name-only` entre a base e o head do PR; entre `before` e `sha` num push) e devolve `rapido=true|false`. O resultado é sempre `false` em `workflow_call`, em `workflow_dispatch` e quando `before` é vazio ou só zeros. Padrões rápidos: `airflow/dags/**` (menos `airflow/dags/utfpr_dengue/pyproject.toml` e `uv.lock`), `airflow/tests/**` (uma DAG nova quase sempre vem com o teste dela, e o job `dags` da via rápida monta os testes do commit), `ml/notebooks/**`, `openspec/**`, `docs/**` e `*.md`. Os jobs `images`, `platform-e2e`, `frontend`, `backend` e `ml-tests` ganham `if: needs.escopo.outputs.rapido != 'true'`. No `ml-models-tests`, o passo `pytest -m models` fica condicional e a verificação dos notebooks roda sempre. Os casos do script são testados no próprio CI (job `lint`), sem rede.

7. **Integridade das DAGs na via rápida com a imagem publicada.** Na via rápida o job `dags` não builda: baixa `anselmomendes/atlas-epidemiologia-airflow:hml` e monta `airflow/dags`, `airflow/tests` e `ml/notebooks` do commit sobre os caminhos da imagem. Isso é válido porque a via rápida garante que nenhum insumo da imagem mudou em relação a `hml`. Fora da via rápida o job continua usando o build do `images`. Alternativa descartada: buildar com o cache do GitHub Actions, que é limitado a 10 GB por repositório e pode estar sem a imagem do Airflow (mais de 10 GB), virando um build completo sem aviso.

8. **`ci-ok` com lista de dispensas.** O `jq` do agregado passa a receber `rapido` e aceita `skipped` só para `images`, `platform-e2e`, `frontend`, `backend` e `ml-tests` quando `rapido=true`, além da regra atual do `promocao`. Qualquer outro pulo continua reprovando.

9. **`ml.yml` ignora notebooks.** O workflow passa a usar `"!ml/notebooks/**"` nos `paths`. O Jupyter de hml só ganha os notebooks novos no próximo build da `ml-notebook` (ele semeia a pasta de trabalho a partir da imagem). Isso é aceito: o Airflow lê os notebooks do git-sync, e o Jupyter é para exploração.

10. **Teste local antes do PR.** `platform/ci/testar-dags.sh` roda `test_dags.py` na imagem local (`atlas-epidemiologia-airflow:local`, ou `:hml` com `--publicada`) com as DAGs e os testes do disco montados. Leva segundos e não precisa do Airflow de pé.

## Risks / Trade-offs

- [Execução completa mais lenta: cada DAG de modelo tem início, fim e polling de 60 s] → Alguns minutos sobre uma execução de horas; o pool continua sendo o gargalo real.
- [DAG de modelo pausada por engano: o orquestrador esperaria até o `dagrun_timeout`] → `iniciar_execucao` não tem acesso ao banco no Airflow 3. Mitigação: `is_paused_upon_creation=False`, o README avisa, e o disparo usa `execution_timeout` de 8 h por modelo, para falhar antes do fim da execução inteira.
- [Ensemble sozinho pegando bases de outra janela ou semente] → A busca filtra pela versão da gold e registra no log as runs escolhidas, com janela e semente. A divergência de parâmetros é aceita no disparo isolado, que serve para depuração.
- [Via rápida liberando algo que só o e2e pegaria] → O e2e cobre a DAG de exemplo e o MLflow, não as DAGs de previsão. O push em `hml` depois do merge também roda na via rápida, então o primeiro pipeline completo seguinte (qualquer mudança fora dos padrões) volta a cobrir tudo. Aceito pela velocidade.
- [Imagem `:hml` diferente do que o PR espera (por exemplo, publicação de `hml` em andamento)] → O caso é raro; uma falha nesse cenário se resolve rodando o PR de novo depois da publicação.
- [Run IDs fixos (`<run_id>__<modelo>`) colidindo numa nova tentativa] → `reset_dag_run=True` substitui a run anterior daquele modelo.

## Migration Plan

1. Implementar e testar (fábrica, seis DAGs, orquestrador, testes de DAG, CI). Rodar `testar-dags.sh` localmente.
2. Pré-requisito em hml: o `airflow-dag-processor` na imagem atual (redeploy com *re-pull*, com a aprovação do usuário).
3. PR `dev` → `hml`. Esse PR muda workflows, então roda o pipeline completo. Depois do merge, conferir no Airflow de hml as seis DAGs despausadas e o orquestrador sem `horizonte.train_*`.
4. Disparar uma DAG de modelo leve sozinha (SVR, horizonte 1) e depois o orquestrador completo.
5. Validar a via rápida com um PR que muda só uma docstring de DAG.

Rollback: reverter o merge em `hml`. O git-sync volta à DAG única em até 60 s. As DAGs de modelo somem da lista (ficam marcadas como obsoletas) e as runs do MLflow não mudam.
