<#
.SYNOPSIS
  Plataforma de ML local (Postgres + MLflow + Airflow [+ Jupyter]).

.EXAMPLE
  ./platform/dev.ps1 up              # build + sobe tudo (MLflow :5000, Airflow :8080)
  ./platform/dev.ps1 status          # estado e saúde dos serviços
  ./platform/dev.ps1 logs mlflow     # acompanha os logs de um serviço
  ./platform/dev.ps1 notebook        # sobe também o JupyterLab (:8888)
  ./platform/dev.ps1 down            # para tudo (mantém os dados)
  ./platform/dev.ps1 reset           # para tudo e APAGA volumes (runs, histórico, artefatos locais)
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('up', 'down', 'status', 'logs', 'notebook', 'reset')]
    [string]$Command = 'status',
    [Parameter(Position = 1)]
    [string]$Service
)

$ErrorActionPreference = 'Stop'
$Platform = $PSScriptRoot
$Root = Split-Path $Platform -Parent
# Um único .env, na raiz (modelo: .env.example); ignorado pelo Git
$EnvFile = Join-Path $Root '.env'
$OldEnvFile = Join-Path $Platform '.env'

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $OldEnvFile) {
        Copy-Item $OldEnvFile $EnvFile
        Write-Host "Copiei platform/.env para .env (agora o arquivo é um só, na raiz). Compare com o .env.example e acrescente as variáveis novas." -ForegroundColor Yellow
    } else {
        Copy-Item (Join-Path $Root '.env.example') $EnvFile
        Write-Host "Criei .env a partir do .env.example. Troque as senhas e rode de novo." -ForegroundColor Yellow
        exit 1
    }
}

# Commit do código em uso: vai para as imagens e para a tag atlas.git_sha das runs
$env:ATLAS_GIT_SHA = (git -C $Root rev-parse HEAD).Trim()
New-Item -ItemType Directory -Force (Join-Path $Platform 'secrets') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root 'ml/notebooks') | Out-Null

$ComposeFiles = @('-f', (Join-Path $Platform 'compose.dev.yml'))

# CA corporativa opcional (inspeção TLS): gera certs/ca-bundle.pem e aplica compose.ca.yml
$ExtraCa = (Get-Content $EnvFile | Where-Object { $_ -match '^\s*EXTRA_CA_PATH=' }) -replace '^\s*EXTRA_CA_PATH=', ''
if ($ExtraCa) {
    $ExtraCaPath = if ([System.IO.Path]::IsPathRooted($ExtraCa)) { $ExtraCa } else { Join-Path $Platform $ExtraCa }
    if (-not (Test-Path $ExtraCaPath)) { throw "EXTRA_CA_PATH aponta para um arquivo inexistente: $ExtraCaPath" }
    $Certs = Join-Path $Platform 'certs'
    New-Item -ItemType Directory -Force $Certs | Out-Null
    # Na primeira vez o docker baixa a imagem e escreve o progresso em stderr; no PowerShell 5.1
    # com 'Stop' isso viraria erro. O stderr fica de fora do bundle; o código de saída decide.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $Public = docker run --rm --entrypoint cat python:3.12-slim /etc/ssl/certs/ca-certificates.crt 2>$null }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0 -or -not $Public) { throw "Não consegui ler os certificados públicos de python:3.12-slim." }
    $Bundle = ($Public -join "`n") + "`n" + (Get-Content $ExtraCaPath -Raw)
    [System.IO.File]::WriteAllText((Join-Path $Certs 'ca-bundle.pem'), $Bundle)
    $ComposeFiles += @('-f', (Join-Path $Platform 'compose.ca.yml'))
    Write-Host "CA corporativa aplicada ($ExtraCaPath)" -ForegroundColor DarkGray
}

function Invoke-Compose {
    # O docker escreve progresso em stderr; no PowerShell 5.1 isso viraria erro com 'Stop'.
    # Quem decide sucesso/falha é o código de saída.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & docker compose @ComposeFiles --env-file $EnvFile @args 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Command) {
    'up' {
        Invoke-Compose up -d --build
        Invoke-Compose ps --format 'table {{.Service}}\t{{.Status}}'
        Write-Host "`nMLflow:  http://127.0.0.1:5000" -ForegroundColor Green
        Write-Host "Airflow: http://127.0.0.1:8080  (usuário admin; senha = AIRFLOW_ADMIN_PASSWORD do .env)" -ForegroundColor Green
    }
    'status' { Invoke-Compose ps -a --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' }
    'logs' {
        if ($Service) { Invoke-Compose logs -f --tail 200 $Service } else { Invoke-Compose logs -f --tail 50 }
    }
    'notebook' {
        Invoke-Compose --profile notebook up -d --build jupyter
        $Token = (Get-Content $EnvFile | Where-Object { $_ -match '^\s*JUPYTER_TOKEN=' }) -replace '^\s*JUPYTER_TOKEN=', ''
        if (-not $Token) { $Token = 'atlas' }
        Write-Host "JupyterLab: http://127.0.0.1:8888/lab?token=$Token" -ForegroundColor Green
    }
    'down' { Invoke-Compose --profile notebook down }
    'reset' {
        $Answer = Read-Host "Isto APAGA runs, histórico do Airflow e artefatos locais. Digite 'apagar' para confirmar"
        if ($Answer -ne 'apagar') { Write-Host 'Cancelado.'; exit 0 }
        Invoke-Compose --profile notebook down -v
    }
}
