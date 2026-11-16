"""Modelos de previsão de dengue. Cada pasta tem `model.py` (com `build(cfg, **kw)`) e README.

Os imports são preguiçosos: CatBoost, PyTorch, PyMC e Chronos só são carregados quando o
modelo correspondente é treinado (grupo opcional `models` do pyproject).
"""

from __future__ import annotations

import importlib
from typing import Any

from atlas_ml.forecast.base import ModelFactory
from atlas_ml.forecast.config import ForecastConfig

BASE_MODELS = ("baseline_bayes", "catboost", "svr", "lstm", "chronos")
STACKED = ("catboost", "svr", "lstm")  # modelos cujas OOF alimentam o ensemble
MODELS = (*BASE_MODELS, "ensemble")


def get_factory(name: str, **kwargs: Any) -> ModelFactory:
    """Devolve `cfg -> modelo` para o nome dado (kwargs vão para o `build` do modelo)."""
    if name not in MODELS:
        raise ValueError(f"modelo desconhecido '{name}'. Disponíveis: {', '.join(MODELS)}")
    module = importlib.import_module(f"atlas_ml.models.{name}.model")

    def factory(cfg: ForecastConfig):
        return module.build(cfg, **kwargs)

    return factory
