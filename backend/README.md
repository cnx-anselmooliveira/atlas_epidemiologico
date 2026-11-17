# Backend: API gold do Atlas da Dengue

API HTTP **somente leitura** que serve as tabelas gold do BigQuery ao site (`frontend/`, Astro SSR). O site chama a API pela rede interna, e o navegador não fala com ela.

- Leitura direta do BigQuery (dataset `gold`), sem cópia local.
- Os filtros vão como parâmetros de consulta, nunca no texto do SQL. Só as colunas da whitelist (`app/tables.py`) são filtráveis.
- Cada consulta tem um teto de bytes faturados (`MAX_BYTES_BILLED`).
- O cache Redis é opcional. A chave de cada resposta inclui a "geração" da tabela, que é o `last_modified` do metadado e não tem custo de consulta. Quando o dbt reconstrói a tabela, as respostas novas aparecem em até `GENERATION_TTL_SECONDS`. Se o Redis cair, a API continua consultando o BigQuery direto.

## Rotas

| Rota | Tabela | Filtros | Ordem |
|---|---|---|---|
| `GET /gold/casos-provaveis-brasil-semanal` | `gold_dengue_casos_provaveis_brasil_semanal` | `epi_year` | `week_start` |
| `GET /gold/casos-provaveis-uf-semanal` | `gold_dengue_casos_provaveis_uf_semanal` | `uf`, `epi_year` | `week_start`, `uf` |
| `GET /health` | — | — | — |

Regras das rotas `/gold/*`:
- `limit` tem padrão 200 e máximo 1000; acima disso, a resposta é 422.
- `offset` começa em 0.
- A resposta é uma lista JSON.
- Se o BigQuery falhar, a resposta é 503.

O `/health` responde 200 com `{"bigquery": "ok", "cache": "ok|desligado|indisponivel"}`, ou 503 se o BigQuery estiver inacessível.

Cada linha traz `week_start`, `epi_year`, `epi_week`, `notified_cases`, `probable_cases`, `confirmed_cases`, `alarm_cases`, `severe_cases`, `deaths`, `population`, `incidence` e `gold_generated_at`. A rota por UF traz também `uf`.

As rotas herdadas da API antiga (América do Sul) entram depois, na mudança `decouple-architecture-bigquery` (tarefa 5.3).

## Variáveis

| Variável | Padrão | Uso |
|---|---|---|
| `GCP_PROJECT` | `ppgcc-dengue-project` | projeto do BigQuery |
| `BQ_DATASET_GOLD` | `gold` | dataset das tabelas |
| `BQ_LOCATION` | — | localização dos jobs (opcional) |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | caminho da chave da service account (local) |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | — | o JSON inteiro da chave (variável de stack no Portainer) |
| `MAX_BYTES_BILLED` | 1 GiB | teto de bytes faturados por consulta |
| `REDIS_URL` | — | `redis://redis:6379/0`; vazio desliga o cache |
| `CACHE_TTL_SECONDS` | 86400 | validade máxima de uma resposta no cache |
| `GENERATION_TTL_SECONDS` | 300 | de quanto em quanto tempo a geração da tabela é relida |

Nenhuma chave vai para a imagem ou para o repositório.

## Rodar localmente

```sh
cd backend
uv sync
GOOGLE_APPLICATION_CREDENTIALS=../platform/secrets/training-sa.json \
  uv run uvicorn app.main:create_app --factory --port 8000
curl "http://localhost:8000/gold/casos-provaveis-uf-semanal?uf=SP&limit=5"
```

Com Redis, em container, a API faz parte da stack local da plataforma (serviços `backend` e `redis`):
- o código de `backend/app` é montado ao vivo, com `--reload`;
- a chave vem de `platform/secrets/training-sa.json`, montada só em runtime;
- a CA corporativa entra pelo `compose.ca.yml`, quando configurada.

```powershell
./platform/dev.ps1 up            # sobe tudo, incluindo a API em 127.0.0.1:8000
./platform/dev.ps1 logs backend
curl "http://localhost:8000/health"
```

Build avulso da imagem (rede com inspeção TLS: `--secret id=extra_ca,src=platform/certs/ca-bundle.pem`):

```sh
docker build -t atlas-epidemiologia-backend:local backend
```

## Testes

```sh
uv run pytest       # sem BigQuery: repositório falso + fakeredis
uv run ruff check . && uv run ruff format --check .
```
