# Tasks

## 1. Modelos: horizontes, previsão do futuro e figuras (`ml/`)

- [x] 1.1 Parametrizar o nome do modelo registrado por horizonte (`atlas-br-<modelo>-h<H>`) em `run_model`/`register_model` e validar `horizon` entre 1 e 4 em `ForecastConfig`; o Ensemble exige runs-base do mesmo horizonte e snapshot; verificar com testes de `pytest` (registro com horizonte 3, recusa de base com horizonte diferente)
- [x] 1.2 Criar `build_future_windows(panel, cfg)` (janela das últimas `window` semanas maduras por UF, `target_date = origem + horizon`) e `predict_future` em `base.py`, gravando `future_predictions.parquet` com `uf, origin_date, target_date, horizon, y_pred, lower, upper` (sem negativos); verificar com teste sintético: 27 UFs, origem = última semana madura, nenhuma linha usa dado posterior à origem
- [x] 1.3 Implementar `predict_future` específico do Chronos (histórico longo, `prediction_length` = horizonte) e do Bayesiano (`v_ano` do ano do alvo); verificar com testes sintéticos de contrato dos dois (colunas, escala, sem negativos)
  - Resultado: não foi preciso código específico. Chronos e Bayesiano montam a previsão só pela janela e pela origem (o Bayesiano já usa a priori para ano novo), então servem à janela do futuro como os demais; o contrato foi coberto pelos testes de `predict_future` com os seis modelos.
- [x] 1.4 Incluir `horizon` em `metrics_by_uf.csv` e nas métricas logadas; verificar com teste que dois horizontes do mesmo modelo geram métricas independentes
- [x] 1.5 Criar `atlas_ml/forecast/figures.py` (matplotlib `Agg`, tema claro, português, PNG ≤ 500 KB) com as figuras comuns e uma por família, cada uma num `try` que registra `atlas.figures_failed`; adicionar `matplotlib` ao grupo `models`; verificar com testes: as 3 figuras de cada modelo sobre dados sintéticos, tamanho ≤ 500 KB e falha forçada sem derrubar a run
- [x] 1.6 Ligar previsão do futuro e figuras ao fim de `run_model` e expor `--horizon` no CLI (`atlas-ml forecast train <modelo> --horizon H`); verificar com `uv run pytest` e uma run local de um modelo leve (SVR) a `horizon=2` no MLflow de dev, conferindo `future_predictions.parquet` e `figures/` na run

## 2. DAG de treino por horizonte

- [x] 2.1 Reescrever `atlas_dengue_forecast_br` em TaskFlow chamando as funções de `atlas_ml` (sem `BashOperator`), com parâmetro `horizons` (padrão 1 a 4), a cadeia dos seis modelos por horizonte em task groups mapeados, `compare` por horizonte (`all_done`) e disparo da exportação ao fim; verificar com `test_dags.py` atualizado (estrutura, mapeamento, regras de gatilho, sem `BashOperator`)
- [ ] 2.2 Treinar os seis modelos nos 4 horizontes em dev (com `drop_recent_weeks=8`) e registrar tempo total, por modelo e as métricas em `docs/referencias/resultados-forecast-br.md`; verificar no MLflow 24 versões `atlas-br-<modelo>-h<H>@dev` e `future_predictions.parquet` e `figures/` em cada run

## 3. Exportação do MLflow para o BigQuery

- [x] 3.1 Criar `atlas_ingest/forecast_export.py` com as funções puras (versão vigente pelo alias, linha `BR` ponderada pela população e métricas recalculadas, validação de figura PNG ≤ 500 KB, conferência da origem comum entre horizontes), sem import de Airflow; verificar com `airflow/tests/test_forecast_export.py` sem rede (casos: BR = soma de casos ÷ população, figura grande rejeitada, horizonte com origem diferente descartado)
- [ ] 3.2 Criar o DDL do dataset `forecast` (tabelas e visões `forecast_current_*`, com descrição de cada coluna, partição por `exported_date` e cluster por `model, horizon`) em `airflow/dags/atlas_ingest/forecast_ddl.py`; verificar criando em dev e conferindo com `bq show --schema`
- [ ] 3.3 Escrever a DAG `process_forecast_export_atlas` (TaskFlow: `listar_versoes` → `extrair` mapeada → `carregar_bigquery` → `publicar_figuras` → `atualizar_visoes`; sem agendamento, `max_active_runs=1`; Connections `mlflow_default` e `google_cloud_default`); verificar com `test_dags.py` (estrutura, mapeamento, sem agendamento, sem `BashOperator`)
- [ ] 3.4 Criar a Connection `mlflow_default` no Airflow de dev (UI) e rodar a DAG com as runs da tarefa 2.2; verificar `forecast_current_model_runs` com 24 linhas, `forecast_current_predictions` com as linhas `future` das 27 UFs e `BR` nos 4 horizontes e as figuras em `gs://ppgcc-bucket/forecast/dev/...`
- [ ] 3.5 Reexecutar a DAG sem mudança no MLflow e, depois, derrubar o MLflow; verificar que a primeira não duplica linhas (contagens iguais) e que a segunda falha sem alterar as tabelas nem vazar credencial no log

## 4. Backend: rotas `/forecast/*`

- [ ] 4.1 Registrar as visões `forecast_current_*` em `app/tables.py` (colunas, filtros `model, horizon, uf, split`, ordem) e criar o roteador `/forecast/models`, `/forecast/metrics-uf` e `/forecast/predictions` com paginação, parâmetros de consulta e o cache por geração; verificar com testes de contrato no padrão de `tests/test_api.py` (filtros, ordem, 422 acima do máximo, lista vazia sem exportação, 503 com BigQuery fora)
- [ ] 4.2 Criar `GET /forecast/figures/{model}/{arquivo}` lendo do bucket só arquivos registrados em `forecast_current_figures`, com `Cache-Control`, `ETag` e sem expor o caminho; verificar com testes (PNG válido, caminho com `..` e arquivo não registrado → 404, cabeçalhos de cache)
- [ ] 4.3 Dar à conta de serviço do backend a leitura do prefixo `forecast/` do bucket (variável de stack, nada no Git) e documentar em `deploy/README.md`; verificar com `curl` local uma figura real e `check-secrets.sh --all` limpo
- [ ] 4.4 Atualizar `backend/README.md` (rotas, filtros, cache, figuras) e rodar contra o BigQuery real; verificar `curl` de `/forecast/models` e de `/forecast/predictions?model=catboost&horizon=2&uf=SP&split=future` com dados da exportação

## 5. Site: página de previsão e documentação dos modelos

- [ ] 5.1 Passar "Previsão" a `disponivel` em `src/data/secoes.ts` (ícone e destaque com o melhor modelo na página inicial) e criar o sprite `public/icons-modelos.svg` com os seis ícones; verificar com `tests/secoes.test.ts` e a inspeção visual dos ícones no tema claro e escuro
- [ ] 5.2 Criar `src/lib/server/forecast.ts` (paginação, timeout, `BackendUnavailableError`, como `gold.ts`), `src/lib/forecast.ts` (agregações: melhor modelo, comparação por NRMSE, erro por horizonte, junção observado + teste + futuro + semanas em consolidação) e `parseModelo`/`parseHorizonte` em `filtros.ts`; verificar com testes Vitest (`?h=9`, `?modelo=xyz`, ordenação, junção) e o mock estendido com as rotas `/forecast/*` e fixtures dos seis modelos
- [ ] 5.3 Criar os componentes `ModelSwitcher`, `ForecastChart`, `MetricCard`/`MetricGrid` e `ModelComparison`; verificar com testes da Container API (seletor com links e desabilitado, gráfico com tabela alternativa, cartões com a explicação das métricas)
- [ ] 5.4 Implementar `/previsao` (filtros por URL, gráfico, cartões, comparação, estados vazio e 503, aviso de previsão como estimativa, rótulo "previsão retroativa" com a semana de origem e data do treino) e o repasse `/previsao/imagens/[modelo]/[arquivo]`; verificar com testes da Container API (padrões, `?modelo=lstm&uf=MG&h=3` preservado, vazio, 503)
- [ ] 5.5 Escrever os textos de `src/content/modelos/*.md` dos seis modelos (explicação breve, entradas, alvo, hiperparâmetros, referência) e a página `/previsao/modelos/[modelo]` com métricas por horizonte e por UF e as figuras (legenda e texto alternativo, estado "sem figuras"); verificar com testes da Container API para cada modelo e para o modelo ausente (404)
  - Já feito: `ComoPrevemos.astro`, o esquema "como a previsão é feita" (janela de 12 semanas, origem, 4 horizontes e as semanas incompletas), com a origem por parâmetro, para entrar na documentação de cada modelo e na página de previsão; testado na Container API e conferido no desktop e a 360 px.
- [ ] 5.6 Estender o smoke do Playwright: 360 px sem rolagem em `/previsao` e na documentação, troca de modelo mantendo UF e horizonte, `/previsao` sem JavaScript com a tabela das próximas semanas, botão de informação abrindo a documentação; verificar com `npm run test:e2e` em verde e `npm run lint`, `npm run check`

## 6. Integração, documentação e entrega

- [ ] 6.1 Conferir os números da página com o BigQuery e com o MLflow (NRMSE de teste e a previsão da primeira semana futura de um modelo, em duas UFs e no Brasil) e registrar em `docs/referencias/previsao-no-site.md`, junto do desenho do fluxo e de onde ficam as credenciais; verificar as comparações no documento
- [ ] 6.2 Adicionar ao `deploy/README.md` as Connections (`mlflow_default`, `google_cloud_default`) e variáveis de stack de hml para a exportação e o backend; verificar com `bash platform/ci/check-secrets.sh --all` sem achados
- [ ] 6.3 Commits por módulo em `dev` (`feat(ml)`, `feat(airflow)`, `feat(backend)`, `feat(frontend)`, `docs`) e validação com `openspec validate add-forecast-page --strict`; verificar `git log --oneline` e o CI da `dev` verde

## Workflow follow-up

- Promover para `hml` pelo fluxo normal e criar as Connections e variáveis de hml pela interface.
- Arquivar a mudança depois de a página estar validada em hml.
