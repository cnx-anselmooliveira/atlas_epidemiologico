"""DAG do Airflow atlas_forecast_svr: treina o modelo nos horizontes pedidos e registra no MLflow.

Disparada pelo orquestrador atlas_dengue_forecast_br (processo completo) ou à mão (só treina e
registra). A DAG é montada por atlas_ingest/forecast_modelo.py, igual para os seis modelos.
"""

from atlas_ingest.forecast_modelo import criar_dag_modelo

dag = criar_dag_modelo("svr")
