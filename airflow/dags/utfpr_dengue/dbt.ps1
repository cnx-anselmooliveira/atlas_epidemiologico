# Roda o dbt do projeto utfpr_dengue localmente, com o mesmo profile da DAG process_etl_atlas.
#   ./airflow/dags/utfpr_dengue/dbt.ps1 debug
#   ./airflow/dags/utfpr_dengue/dbt.ps1 build --select +gold_dengue_casos_provaveis_uf_semanal
# Padrões (sobrescreva definindo antes):
#   DBT_BQ_KEYFILE  <repo>/platform/secrets/training-sa.json
#   artefatos       <repo>/.dbt-local/{target,logs,dbt_packages} (ignorado pelo git)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Here '../../..')).Path
function Set-Default($Name, $Value) {
    if (-not [Environment]::GetEnvironmentVariable($Name)) { [Environment]::SetEnvironmentVariable($Name, $Value) }
}
Set-Default 'DBT_BQ_KEYFILE' (Join-Path $Repo 'platform/secrets/training-sa.json')
Set-Default 'DBT_TARGET_PATH' (Join-Path $Repo '.dbt-local/target')
Set-Default 'DBT_LOG_PATH' (Join-Path $Repo '.dbt-local/logs')
Set-Default 'DBT_PACKAGES_INSTALL_PATH' (Join-Path $Repo '.dbt-local/dbt_packages')
$env:DBT_SEND_ANONYMOUS_USAGE_STATS = 'false'
# venv do uv fora da pasta de DAGs: o Cosmos calcula um hash da pasta do projeto a cada
# leitura da DAG, e um .venv aqui dentro deixaria isso lento demais (montagem do Windows)
Set-Default 'UV_PROJECT_ENVIRONMENT' (Join-Path $Repo '.dbt-local/venv')
& uv run --native-tls --project $Here dbt @args --project-dir $Here --profiles-dir $Here
exit $LASTEXITCODE
