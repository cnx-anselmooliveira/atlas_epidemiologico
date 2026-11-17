"""Configuração dos modelos de previsão (registrada como parâmetros de cada run)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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
    features: tuple[str, ...] = field(default_factory=tuple)  # covariáveis extras do painel

    def __post_init__(self) -> None:
        if self.window < 1 or self.horizon < 1:
            raise ValueError("window e horizon devem ser >= 1")
        if self.test_weeks < 1 or self.val_weeks < 1:
            raise ValueError("test_weeks e val_weeks devem ser >= 1")

    def as_params(self) -> dict[str, object]:
        params = asdict(self)
        params["features"] = ",".join(self.features) or "-"
        return params
