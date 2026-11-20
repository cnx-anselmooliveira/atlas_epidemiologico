"""Esquema do dataset `forecast` do BigQuery (mantido pela DAG process_forecast_export_atlas).

As tabelas guardam o histórico de cada versão exportada; o que vale agora é definido pela
tabela `forecast_current_pointer` (uma linha por modelo e horizonte) e pelas visões
`forecast_current_*`, que a API lê. A visão só muda no fim da exportação, então uma execução que
falha no meio deixa o site com a exportação anterior.
"""

from __future__ import annotations

from google.cloud import bigquery

SF = bigquery.SchemaField

# Colunas de chave das tabelas de dados (todas têm mlflow_run_id, model e horizon)
TABELAS: dict[str, list[bigquery.SchemaField]] = {
    "forecast_model_runs": [
        SF(
            "model",
            "STRING",
            "REQUIRED",
            description="Modelo: baseline_bayes, catboost, svr, lstm, chronos, ensemble.",
        ),
        SF("horizon", "INT64", "REQUIRED", description="Semanas à frente do alvo (1 a 4)."),
        SF(
            "family",
            "STRING",
            description="Família do modelo (gbm, kernel, rnn, bayes, foundation, stacking).",
        ),
        SF(
            "model_version",
            "STRING",
            description="Versão registrada no MLflow (atlas-br-<modelo>-h<H>, com _dev ou _hml).",
        ),
        SF("mlflow_run_id", "STRING", "REQUIRED", description="Run do MLflow que originou a versão."),
        SF("data_version", "STRING", description="Versão dos dados do treino (snapshot da gold)."),
        SF("trained_at", "TIMESTAMP", description="Início do treino."),
        SF("env", "STRING", description="Ambiente cujo alias foi exportado (dev, hml ou prod)."),
        SF("params", "STRING", description="Parâmetros da run (JSON)."),
        SF("figures_failed", "STRING", description="Figuras que falharam no treino, separadas por vírgula."),
        SF("exported_at", "TIMESTAMP", "REQUIRED", description="Quando a exportação gravou a linha."),
    ],
    "forecast_metrics": [
        SF("model", "STRING", "REQUIRED"),
        SF("horizon", "INT64", "REQUIRED"),
        SF("mlflow_run_id", "STRING", "REQUIRED"),
        SF("split", "STRING", "REQUIRED", description="val ou test."),
        SF("nrmse", "FLOAT64", description="Média entre UFs do NRMSE (RMSE / amplitude observada)."),
        SF("mae", "FLOAT64", description="Média entre UFs do erro absoluto médio (casos por 100 mil)."),
        SF("rmse", "FLOAT64", description="Média entre UFs da raiz do erro quadrático médio."),
        SF("r2", "FLOAT64", description="Média entre UFs do R²."),
        SF("interval_coverage", "FLOAT64", description="Parte dos observados dentro do intervalo previsto."),
        SF("fit_seconds", "FLOAT64", description="Tempo de treino em segundos."),
        SF("nrmse_br", "FLOAT64", description="NRMSE da série agregada do Brasil."),
        SF("exported_at", "TIMESTAMP", "REQUIRED"),
    ],
    "forecast_metrics_uf": [
        SF("model", "STRING", "REQUIRED"),
        SF("horizon", "INT64", "REQUIRED"),
        SF("mlflow_run_id", "STRING", "REQUIRED"),
        SF("split", "STRING", "REQUIRED"),
        SF("uf", "STRING", "REQUIRED", description="Sigla da UF ou BR (série agregada)."),
        SF("n", "INT64", description="Semanas avaliadas."),
        SF("nrmse", "FLOAT64"),
        SF("mae", "FLOAT64"),
        SF("rmse", "FLOAT64"),
        SF("r2", "FLOAT64"),
        SF("exported_at", "TIMESTAMP", "REQUIRED"),
    ],
    "forecast_predictions": [
        SF("model", "STRING", "REQUIRED"),
        SF("horizon", "INT64", "REQUIRED"),
        SF("mlflow_run_id", "STRING", "REQUIRED"),
        SF(
            "split",
            "STRING",
            "REQUIRED",
            description="val, test ou future (semana após a origem, sem observado).",
        ),
        SF(
            "uf",
            "STRING",
            "REQUIRED",
            description="Sigla da UF ou BR (média ponderada pela população, sem intervalo).",
        ),
        SF("origin_date", "DATE", description="Domingo da última semana do histórico usado na previsão."),
        SF("target_date", "DATE", "REQUIRED", description="Domingo da semana prevista."),
        SF("y_true", "FLOAT64", description="Incidência observada por 100 mil (nulo em future)."),
        SF("y_pred", "FLOAT64", description="Incidência prevista por 100 mil."),
        SF("lower", "FLOAT64", description="Limite inferior do intervalo (nulo quando o modelo não produz)."),
        SF("upper", "FLOAT64", description="Limite superior do intervalo."),
        SF("population", "FLOAT64", description="População da UF na semana."),
        SF("exported_at", "TIMESTAMP", "REQUIRED"),
    ],
    "forecast_figures": [
        SF("model", "STRING", "REQUIRED"),
        SF("horizon", "INT64", "REQUIRED"),
        SF("mlflow_run_id", "STRING", "REQUIRED"),
        SF("name", "STRING", "REQUIRED", description="Nome do arquivo PNG."),
        SF("caption", "STRING", description="Legenda em português."),
        SF("gcs_path", "STRING", "REQUIRED", description="Objeto no bucket (nunca exposto pela API)."),
        SF("size_bytes", "INT64"),
        SF("exported_at", "TIMESTAMP", "REQUIRED"),
    ],
}

# Colunas repetidas nas tabelas: a descrição é a mesma em todas
_COMUNS = {
    "model": "Modelo: baseline_bayes, catboost, svr, lstm, chronos ou ensemble.",
    "horizon": "Semanas à frente do alvo (1 a 4).",
    "mlflow_run_id": "Run do MLflow que originou a linha.",
    "exported_at": "Quando a DAG de exportação gravou a linha.",
    "split": "val, test ou future.",
    "nrmse": "NRMSE: RMSE dividido pela amplitude observada (menor é melhor).",
    "mae": "Erro absoluto médio, em casos por 100 mil habitantes.",
    "rmse": "Raiz do erro quadrático médio, em casos por 100 mil habitantes.",
    "r2": "Coeficiente de determinação (R²).",
}


def _descrever(schema: list[bigquery.SchemaField]) -> list[bigquery.SchemaField]:
    return [
        f if f.description else SF(f.name, f.field_type, f.mode, description=_COMUNS.get(f.name, f.name))
        for f in schema
    ]


TABELAS = {nome: _descrever(schema) for nome, schema in TABELAS.items()}

POINTER = "forecast_current_pointer"
POINTER_SCHEMA = _descrever(
    [
        SF("model", "STRING", "REQUIRED"),
        SF("horizon", "INT64", "REQUIRED"),
        SF("mlflow_run_id", "STRING", "REQUIRED", description="Run vigente do modelo e horizonte."),
        SF("exported_at", "TIMESTAMP", "REQUIRED"),
    ]
)


def colunas(tabela: str) -> list[str]:
    """Nomes das colunas da tabela, sem `exported_at` (que a carga acrescenta)."""
    return [f.name for f in TABELAS[tabela] if f.name != "exported_at"]


def sql_visao(project: str, dataset: str, tabela: str) -> str:
    """Visão `forecast_current_<resto>`: só as linhas da run vigente de cada modelo e horizonte."""
    nome = tabela.removeprefix("forecast_")
    return (
        f"CREATE OR REPLACE VIEW `{project}.{dataset}.forecast_current_{nome}` AS\n"
        f"SELECT t.*\nFROM `{project}.{dataset}.{tabela}` AS t\n"
        f"JOIN `{project}.{dataset}.{POINTER}` AS p USING (model, horizon, mlflow_run_id)"
    )


def sql_visao_modelos(project: str, dataset: str) -> str:
    """Visão para `/forecast/models`: uma linha por modelo e horizonte com as métricas de teste."""
    return (
        f"CREATE OR REPLACE VIEW `{project}.{dataset}.forecast_current_models` AS\n"
        "SELECT r.model, r.horizon, r.family, r.model_version, r.data_version, r.trained_at, r.env,\n"
        "       r.mlflow_run_id, m.nrmse, m.mae, m.rmse, m.r2, m.interval_coverage,\n"
        "       m.fit_seconds, m.nrmse_br\n"
        f"FROM `{project}.{dataset}.forecast_current_model_runs` AS r\n"
        f"LEFT JOIN `{project}.{dataset}.forecast_current_metrics` AS m\n"
        "  ON m.model = r.model AND m.horizon = r.horizon\n"
        "  AND m.mlflow_run_id = r.mlflow_run_id AND m.split = 'test'"
    )


def _atualizar_descricoes(client: bigquery.Client, ref, schema: list[bigquery.SchemaField]) -> None:
    """Tabela criada antes desta versão: só completa as descrições (o resto do esquema não muda)."""
    atual = client.get_table(ref)
    esperado = {f.name: f.description for f in schema}
    if any(f.description != esperado.get(f.name) for f in atual.schema):
        atual.schema = [
            SF(f.name, f.field_type, f.mode, description=esperado.get(f.name, f.description))
            for f in atual.schema
        ]
        client.update_table(atual, ["schema"])


def garantir_dataset(
    client: bigquery.Client, project: str, dataset: str, location: str | None = None
) -> None:
    """Cria o dataset, as tabelas (particionadas por dia de exportação, agrupadas por modelo e
    horizonte) e o ponteiro, se ainda não existirem. Não altera tabelas existentes."""
    ds = bigquery.Dataset(f"{project}.{dataset}")
    if location:
        ds.location = location
    ds.description = "Previsões de dengue exportadas do MLflow (DAG process_forecast_export_atlas)."
    client.create_dataset(ds, exists_ok=True)
    for nome, schema in TABELAS.items():
        tabela = bigquery.Table(f"{project}.{dataset}.{nome}", schema=schema)
        tabela.time_partitioning = bigquery.TimePartitioning(field="exported_at")
        tabela.clustering_fields = ["model", "horizon"]
        client.create_table(tabela, exists_ok=True)
        _atualizar_descricoes(client, tabela.reference, schema)
    ponteiro = bigquery.Table(f"{project}.{dataset}.{POINTER}", schema=POINTER_SCHEMA)
    client.create_table(ponteiro, exists_ok=True)
    _atualizar_descricoes(client, ponteiro.reference, POINTER_SCHEMA)
