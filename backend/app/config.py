"""Configuração por variáveis de ambiente (nenhuma credencial no código ou na imagem)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gcp_project: str = "ppgcc-dengue-project"
    bq_dataset_gold: str = "gold"
    bq_dataset_forecast: str = "forecast"
    # Figuras dos modelos: só este bucket e o prefixo forecast/ são lidos (conta de leitura própria)
    forecast_bucket: str = "ppgcc-bucket"
    forecast_prefix: str = "forecast/"
    bq_location: str | None = None
    # Credencial: GOOGLE_APPLICATION_CREDENTIALS (caminho, padrão do Google) ou o JSON da
    # service account inteiro nesta variável (variável de stack no Portainer)
    google_application_credentials_json: str | None = None
    # Trava de custo por consulta (bytes faturados); a consulta acima disso falha
    max_bytes_billed: int = 1024**3

    # Vazio desliga o cache (cada requisição consulta o BigQuery)
    redis_url: str | None = None
    redis_timeout_seconds: float = 0.25
    cache_ttl_seconds: int = 24 * 3600
    # Validade da "geração" de cada tabela (last_modified do BigQuery) guardada no Redis:
    # depois de um dbt build, as respostas novas aparecem em até esse tempo
    generation_ttl_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
