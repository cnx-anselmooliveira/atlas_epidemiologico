"""Configuração dos modelos de previsão (registrada como parâmetros de cada run)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

MAX_HORIZON = 4  # o site mostra as próximas 4 semanas

# Canais epidemiológicos da gold (contagens por UF e semana). Entram nas janelas como taxa por
# 100 mil habitantes em log1p, passo a passo, como as variáveis da referência ESA-UNICEF.
# Ficam de fora as colunas de qualidade (other/date_fallback/place_fallback) e de proveniência.
CHANNELS = (
    "notified_cases",
    "discarded_cases",
    "confirmed_cases",
    "alarm_cases",
    "severe_cases",
    "inconclusive_cases",
    "investigation_cases",
    "deaths",
)
# Covariáveis estáticas da UF (repetidas em cada passo da janela, sem log nem taxa)
STATIC_COVARIATES = ("mean_elevation_m", "mean_slope_deg")
DEFAULT_FEATURES = CHANNELS + STATIC_COVARIATES


@dataclass(frozen=True)
class ForecastConfig:
    window: int = 12  # semanas de histórico por janela
    horizon: int = 1  # semanas à frente do alvo
    test_weeks: int = 52  # alvos mais recentes = teste (nunca usado em ajuste)
    val_weeks: int = 52  # alvos anteriores ao teste = validação
    drop_recent_weeks: int = 8  # semanas imaturas (atraso de notificação) descartadas
    oof_folds: int = 3  # blocos finais do treino para previsões out-of-fold
    oof_block_weeks: int = 52
    augment: int = 3  # cópias com ruído gaussiano (só treino; 0 desliga)
    augment_sigma: float = 0.01
    seed: int = 42
    # covariáveis do painel que entram em cada passo da janela (padrão: canais do SINAN + relevo)
    features: tuple[str, ...] = field(default_factory=lambda: DEFAULT_FEATURES)

    def __post_init__(self) -> None:
        if self.window < 1 or self.horizon < 1:
            raise ValueError("window e horizon devem ser >= 1")
        if self.horizon > MAX_HORIZON:
            raise ValueError(f"horizon deve ser de 1 a {MAX_HORIZON} semanas")
        if self.test_weeks < 1 or self.val_weeks < 1:
            raise ValueError("test_weeks e val_weeks devem ser >= 1")

    def as_params(self) -> dict[str, object]:
        params = asdict(self)
        params["features"] = ",".join(self.features) or "-"
        return params
