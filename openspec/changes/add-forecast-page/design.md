# Design

## Context

- **O que o MLflow guarda hoje.** O experimento `atlas/dengue-forecast-br` tem, por execução da DAG `atlas_dengue_forecast_br`, uma run `dataset`, uma run por modelo (`baseline_bayes`, `catboost`, `svr`, `lstm`, `chronos`, `ensemble`) e uma run `compare`. Cada run de modelo registra:
  - parâmetros (`window`, `horizon`, divisões por data, `model.*`) e métricas de validação e teste (`test_nrmse_mean`, `test_mae_mean`, `test_rmse_mean`, `test_r2_mean`, cobertura do intervalo, `fit_seconds`);
  - os artefatos `predictions.parquet` (validação e teste, com `y_true`), `metrics_by_uf.csv`, `oof_predictions.parquet` e o modelo registrado como `atlas-br-<modelo>`;
  - as tags `atlas.pipeline_run`, `atlas.forecast_model`, `atlas.data_version` e `atlas.model_family`.
- **O que não existe.** Previsão do futuro, métricas por horizonte e figuras. Todo o treino é a 1 semana (`horizon=1`); o parâmetro existe, mas a tarefa 9.3 da `add-dengue-forecast-models` (rodar com 4) ficou aberta.
- **Decisão do usuário (17/11/2026): manter a origem na última semana madura.** Como os modelos descartam as 8 últimas semanas, as 4 semanas previstas ficam antes do dado mais recente (com a gold até 25/10, origem em ~30/08 e alvos de ~06/09 a ~27/09). Em vez de estender o horizonte ou modelar o atraso de notificação, a página trata isso como previsão retroativa, comparável com o que depois foi notificado, e o rotula assim. Uma previsão de semanas ainda não observadas fica como evolução futura.
- **Painel de dados.** `gold_dengue_casos_provaveis_uf_semanal` (27 UFs × semanas desde 2000, incidência por 100 mil). Os modelos descartam as 8 últimas semanas (`drop_recent_weeks`, atraso de notificação), então a "origem" da previsão é a última semana **madura**. Como a gold termina em junho de 2026, as semanas previstas hoje já têm notificações parciais.
- **Ciclo de vida dos modelos.** O registro promove `@dev` → `@hml` → `@prod` por alias (`atlas-ml promote`); o site de cada ambiente deve mostrar a versão do alias daquele ambiente.
- **Site e API.** Astro SSR chamando o backend FastAPI (rotas `/gold/*`, whitelist de colunas, parâmetros de consulta, cache Redis por `last_modified` da tabela). Design system Painel copiado em `frontend/src/styles/ds`, ECharts por `<script>` de componente, registro de seções em `src/data/secoes.ts` (Previsão como "em breve").
- **Credenciais.** Chaves e senhas só por Connection e Variables do Airflow e variáveis de stack (`deploy/README.md`).

## Goals / Non-Goals

**Goals:**
- Um caminho único e idempotente do MLflow até a tela: runs → DAG → BigQuery → API (Redis) → site.
- Previsões do futuro e métricas por horizonte comparáveis entre os seis modelos.
- A página funcionar sem JavaScript e sem MLflow no caminho de uma requisição.

**Non-Goals:**
- Servir modelos (inferência online): o site só mostra o que o treino registrou.
- Previsão por município, retreino agendado, comparação entre ambientes na mesma página.
- Reescrever os modelos: só entram horizonte, previsão do futuro e figuras.

## Decisions

### 1. Estratégia direta, um ajuste por horizonte
Cada modelo é treinado separadamente para `horizon` 1, 2, 3 e 4 (decisão do usuário), em vez de realimentar a previsão (recursiva), porque o erro acumulado da recursiva invalidaria as métricas do horizonte 1 para as semanas seguintes. O custo cresce 4 vezes; o Chronos (zero-shot) e o SVR mal sentem, o Bayesiano e o LSTM são os caros (ver Riscos).

O registro passa a ter um modelo registrado por horizonte, `atlas-br-<modelo>-h<H>`, com o alias do ambiente em cada um. Os nomes antigos (`atlas-br-<modelo>`, horizonte 1) continuam existindo e deixam de ser usados. O Ensemble de cada horizonte usa só as runs-base do mesmo horizonte e do mesmo snapshot (regra que já existe, estendida).

### 2. Previsão do futuro por janela sem alvo
`build_windows` hoje só cria janelas com alvo observado. Um construtor novo, `build_future_windows(panel, cfg)`, monta por UF a janela das últimas `window` semanas maduras (a origem é a última semana madura do painel) e marca `target_date = origin + horizon`. Cada modelo prevê essa janela pela mesma interface `predict`, então o Ensemble, o CatBoost, o SVR e o LSTM não mudam de contrato. Para o Chronos e o Bayesiano, que montam o histórico por conta própria, o método `predict_future` é específico (o Bayesiano usa o `v_ano` do ano do alvo, como já faz para o teste).

O resultado vai em `future_predictions.parquet` (`uf`, `origin_date`, `target_date`, `horizon`, `y_pred`, `lower`, `upper`). Com 4 horizontes, as quatro runs juntas dão as 4 semanas seguintes à origem. A origem é a mesma nas quatro (mesmo snapshot), o que a exportação confere e, se divergir, descarta o horizonte com aviso.

### 3. Figuras geradas no treino, num módulo próprio
`atlas_ml/forecast/figures.py` gera PNGs com matplotlib (backend `Agg`, sem tela), no tema claro, com título e legenda em português, e os grava em `figures/` da run:
- comuns: previsto × observado no teste (Brasil) e erro por UF;
- por família: importância das variáveis (CatBoost e Ensemble), curva de aprendizado (LSTM), erro por semana (SVR), posterior dos parâmetros (Bayesiano) e cobertura do intervalo (Chronos).

Cada figura é gerada dentro de um `try`: falha vira a tag `atlas.figures_failed`, nunca derruba a run. `matplotlib` entra no grupo `models`. Limite de 500 KB por PNG (DPI e tamanho fixos), checado no treino e de novo na exportação.

Alternativa descartada: desenhar tudo no site com os dados exportados. Atenderia à consistência visual, mas a decisão do usuário foi importar as figuras do MLflow.

### 4. DAG de exportação em TaskFlow, sem bash
`process_forecast_export_atlas`, sem agendamento, `max_active_runs=1`, disparada por `TriggerDagRunOperator` ao fim da DAG de treino e manualmente. Tarefas:

```
listar_versoes ─► extrair[modelo×horizonte] ─► carregar_bigquery ─► publicar_figuras ─► atualizar_visoes
```

- `listar_versoes`: com `MlflowClient`, para cada `atlas-br-<modelo>-h<H>` lê o alias do ambiente (`ATLAS_ENV`) e a run de origem; devolve a lista e os ausentes.
- `extrair` (mapeada): baixa `predictions.parquet`, `future_predictions.parquet`, `metrics_by_uf.csv` e a lista de `figures/`, e lê parâmetros e métricas. Devolve DataFrames pequenos por XCom como caminhos em arquivo temporário do worker (nunca o conteúdo).
- `carregar_bigquery`: acrescenta a linha `BR` (decisão 6) e grava por `WRITE_TRUNCATE` na partição da run (idempotente) nas tabelas do dataset `forecast`.
- `publicar_figuras`: copia os PNGs válidos para o bucket em `forecast/<ambiente>/<modelo>/h<H>/<run>/` e preenche `forecast_figures`.
- `atualizar_visoes`: recria as visões `forecast_current_*` (a versão vigente é a do alias; o histórico fica nas tabelas).

O ambiente do Airflow não tem o MLflow (ele vive no venv `atlas_ml`, separado por causa das versões), então a leitura é feita por `atlas_ml.forecast.export_read` numa tarefa `@task.external_python` apontando para esse venv. Ela baixa os artefatos para a pasta compartilhada `/opt/airflow/shared` e devolve só um manifesto JSON (versões, métricas, parâmetros e caminhos). A montagem das tabelas e a carga no BigQuery e no bucket ficam no ambiente do Airflow, com pandas e os provedores do Google (`atlas_ingest/forecast_export.py`, funções puras sem import de Airflow). As fórmulas das métricas do Brasil repetem as de `atlas_ml.forecast.evaluate`.

O acesso ao MLflow é por uma Connection HTTP `mlflow_default` (host e, em hml, usuário e senha), o do BigQuery e do bucket por `google_cloud_default`. O código monta o cliente a partir das Connections e nunca lê chave de arquivo do repositório. Os mesmos nomes de Connection valem em dev e em hml, com valores próprios. As funções puras (montar linha `BR`, validar figura, escolher a versão vigente) ficam em `atlas_ingest/forecast_export.py`, sem import de Airflow, e são testadas sem rede.

### 5. Tabelas do dataset `forecast`
Mantidas pela DAG (não pelo dbt: a origem é o MLflow, não outra tabela do warehouse). Cada tabela tem `exported_at` e `mlflow_run_id`; as de dados são particionadas por `exported_date` e agrupadas por `model, horizon`:

| Tabela | Grão | Colunas principais |
|---|---|---|
| `forecast_model_runs` | run | `model, family, horizon, model_version, mlflow_run_id, data_version, trained_at, params (JSON), env` |
| `forecast_metrics` | run × split | `model, horizon, split, nrmse, mae, rmse, r2, interval_coverage, fit_seconds` |
| `forecast_metrics_uf` | run × split × UF | as mesmas métricas por `uf` (inclui `BR`) |
| `forecast_predictions` | run × UF × semana | `split (validation, test, future), uf, origin_date, target_date, y_true, y_pred, lower, upper, population` |
| `forecast_figures` | run × figura | `model, horizon, name, caption, gcs_path` |

Visões `forecast_current_<tabela>`: só a linha de cada (modelo, horizonte) cuja `mlflow_run_id` é a do alias do ambiente na última exportação. O histórico de versões anteriores fica nas tabelas para auditoria.

### 6. Linha do Brasil calculada na exportação
O modelo é por UF; não há previsão nacional. O Brasil (`uf='BR'`) é a soma dos casos previstos pelas UFs dividida pela população total (as colunas `population` e `y_pred` permitem), sem intervalo (os intervalos por UF não se somam). As métricas do Brasil são recalculadas sobre essa série agregada e a observada. Isso é feito na exportação, com função pura testada, e não nas rotas.

### 7. API: tabelas do `forecast` no mesmo repositório
O registro de tabelas do backend (`app/tables.py`) ganha as visões `forecast_current_*`, com colunas, filtros (`model, horizon, uf, split`) e ordenação fixos; as rotas `/forecast/models`, `/forecast/metrics-uf` e `/forecast/predictions` usam o mesmo `consultar_json` com o cache por geração (a geração de uma visão é o `last_modified` das tabelas que ela lê). `/forecast/models` junta `forecast_model_runs` e `forecast_metrics` (teste, `BR`) numa visão própria, evitando junção no código.

`GET /forecast/figures/{model}/{arquivo}`: procura o par (`model`, `arquivo`) em `forecast_current_figures`, lê o PNG do bucket e devolve com `Cache-Control: public, max-age=86400` e `ETag`. O nome do arquivo nunca monta o caminho: só a linha encontrada o faz. O Redis não guarda binários; o cache dessa rota é o HTTP do site e do navegador. A conta de serviço do backend ganha leitura no prefixo `forecast/` do bucket (separada da chave do treino).

O site mostra as figuras por uma rota do próprio Astro (`/previsao/imagens/<modelo>/<arquivo>`) que repassa a do backend, para o navegador falar só com o site (regra da `rebuild-frontend-astro`).

### 8. Site: rotas, estado na URL e componentes
| Rota | Conteúdo |
|---|---|
| `/previsao` | seletor de modelos, filtros (UF, horizonte), gráfico, cartões de métricas, comparação entre modelos, variação do erro com o horizonte |
| `/previsao/modelos/[modelo]` | documentação do modelo |
| `/previsao/imagens/[modelo]/[arquivo]` | repasse da figura |

Estado em `?modelo=catboost&uf=SP&h=2`; valores inválidos voltam ao padrão (primeiro modelo exportado de menor NRMSE, Brasil, horizonte 1) com aviso, como `?uf=` e `?ano=` já fazem. O seletor de modelo são links (`<a>`), então funciona sem JavaScript.

Componentes novos em `src/components/`: `ModelSwitcher` (ícones, selecionado, desabilitado, botão de informação), `ForecastChart` (ECharts: série observada, teste, previsão futura tracejada com faixa de intervalo e semanas em consolidação; tabela alternativa), `MetricCard`/`MetricGrid` (valor, explicação curta, tooltip), `ModelComparison` (tabela ordenada) e `ModelDoc` (seções da documentação). A camada de dados fica em `src/lib/server/forecast.ts` (paginação, timeout, `BackendUnavailableError`, como `gold.ts`) e as agregações em `src/lib/forecast.ts`.

Os ícones dos seis modelos são um sprite próprio, `public/icons-modelos.svg` (desenhados no estilo dos ícones do design system: traço de 2 px, `currentColor`), com um símbolo por família: árvore/boosting, rede neural, vetores de suporte, distribuição bayesiana, fundação temporal e conjunto.

### 9. Documentação dos modelos
O texto de cada modelo (como funciona, entradas, alvo, hiperparâmetros) fica em Markdown versionado em `frontend/src/content/modelos/<modelo>.md`, em linguagem para público não técnico, escrito a partir dos READMEs de `ml/src/atlas_ml/models/*/README.md` (que seguem técnicos e em português). A página junta esse texto com os dados exportados (métricas por horizonte e por UF, hiperparâmetros reais da run em `forecast_model_runs.params`) e as figuras do MLflow. Uma coleção de conteúdo do Astro valida o front matter (nome, família, ícone, referência).

### 10. DAG de treino
`atlas_dengue_forecast_br` passa a receber `horizons` (padrão `[1, 2, 3, 4]`) e roda a cadeia de modelos uma vez por horizonte em task groups mapeados. As tarefas viram TaskFlow chamando as funções do pacote `atlas_ml` (hoje são `BashOperator` com `atlas-ml forecast ...`), o que cumpre, para essa DAG, o pedido de DAGs escritas como DAGs. O treino de um horizonte que falha não impede os outros; o `compare` passa a comparar por horizonte. Ao fim, dispara a DAG de exportação (`trigger_rule="none_failed_min_one_success"`).

### 11. Ambientes e credenciais
Cada ambiente exporta a versão do **seu** alias (`@dev` em dev, `@hml` em hml, `@prod` em prod) para o **seu** dataset e prefixo do bucket (`forecast` / `forecast/<ambiente>/`). O site de cada ambiente aponta para o backend do mesmo ambiente. Credenciais: Connection `mlflow_default` (com usuário e senha em hml) e `google_cloud_default` criadas na UI do Airflow; variável de stack do backend com a leitura do bucket. Nada disso entra no Git (o job `secrets` do CI protege).

## Risks / Trade-offs

- [Treino ~4 vezes maior, com o PyMC e o LSTM como gargalos] → horizontes em paralelo limitado por `max_active_tasks`, `nutpie` com poucas cadeias e épocas do LSTM já com parada antecipada; o `compare` aceita horizonte faltando.
- [A previsão das 4 semanas é retroativa: a origem é a última semana madura, 8 semanas antes da mais recente] → decisão do usuário de manter; a página rotula as semanas como "previsão retroativa", mostra os valores já observados em consolidação junto da previsão e informa a semana de origem e a data do último treino e dos dados. Uma previsão além da última semana com dados (horizonte de 9 a 12 semanas ou correção do atraso) fica como evolução.
- [Chronos baixa o checkpoint do Hugging Face a cada ambiente novo] → cache `HF_HOME` já existente; a exportação não depende dele.
- [Figuras divergirem do dado exibido] → as figuras e as métricas vêm da mesma run, e a página mostra a versão e a data do treino ao lado.
- [Exportação parcial deixar o site inconsistente] → a visão vigente só muda na última tarefa (`atualizar_visoes`); falha antes disso mantém a exportação anterior.
- [A chave de leitura do bucket no backend aumenta a superfície] → conta de serviço própria, só leitura em `forecast/`, variável de stack no Portainer.
- [Linha `BR` calculada, não prevista pelo modelo] → rotulada na página como "soma das UFs", sem intervalo.

## Migration Plan

1. Mudanças no `ml/` e na DAG de treino, validadas com dados sintéticos (`forecast.synthetic`) e depois um treino completo em dev.
2. Criar o dataset `forecast` (DDL versionado) e a DAG de exportação; rodar em dev com as runs novas.
3. Rotas do backend e a página, desenvolvidas contra o backend mock do site e depois contra a API real.
4. Promover para hml pelo fluxo normal (`dev` → `hml`), criando as Connections de hml pela UI do Airflow e as variáveis de stack no Portainer.
5. **Rollback:** voltar a seção "Previsão" para "em breve" no registro de seções; as tabelas e a DAG podem ficar sem uso.

## Open Questions

- Texto final de cada modelo para público não técnico (revisão do orientador).
- Se o `compare` por horizonte continua a gerar uma run por horizonte ou uma só com a tabela completa.
