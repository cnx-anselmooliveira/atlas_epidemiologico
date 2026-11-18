"""Figuras PNG de cada modelo, gravadas como artefatos da run (pasta `figures/`).

Três por modelo: as duas comuns (previsto × observado no Brasil e erro por UF) e uma da família.
Título e legenda em português, tema claro, até 500 KB cada. Cada figura é gerada isolada: se uma
falha, a run segue e a tag `atlas.figures_failed` lista as que faltaram (spec forecast-future-outputs).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MAX_BYTES = 500 * 1024
CAPTIONS = "captions.json"

AZUL, CINZA, ROSA = "#016ca6", "#676b72", "#c0408a"

# nome do arquivo → legenda (usada pela exportação e pela documentação do site)
COMMON = {
    "forecast_vs_observed.png": "Incidência semanal no Brasil no teste: observado × previsto pelo modelo.",
    "error_by_uf.png": "Erro de cada UF no teste (NRMSE: erro pela amplitude da série; menor é melhor).",
}
FAMILY = {
    "gbm": (
        "feature_importance.png",
        "Variáveis que mais pesam nas decisões do modelo (importância das árvores).",
    ),
    "stacking": (
        "feature_importance.png",
        "Quanto o Ensemble confia em cada previsão-base e em cada extrapolação (importância no meta-modelo).",
    ),
    "rnn": (
        "learning_curve.png",
        "Erro de validação a cada época do treino; o treino para quando deixa de melhorar.",
    ),
    "kernel": (
        "error_by_week.png",
        "Erro absoluto médio por semana no teste (média das UFs, ponderada pela população).",
    ),
    "bayes": (
        "posterior.png",
        "Distribuição posterior de três parâmetros: nível geral, peso da semana anterior e dispersão.",
    ),
    "foundation": (
        "interval_coverage.png",
        "Parte dos valores observados dentro do intervalo previsto, por UF (o ideal é o nível do intervalo).",
    ),
}


def _plt():
    import matplotlib

    matplotlib.use("Agg")  # sem tela
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.figsize": (8, 4.5),
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 10,
        }
    )
    return plt


def _save(fig, path: Path) -> None:
    """PNG com tamanho fixo; reduz o DPI se passar do limite e falha se ainda não couber."""
    for dpi in (100, 80, 60):
        fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        if path.stat().st_size <= MAX_BYTES:
            return
    raise ValueError(f"{path.name} passa de {MAX_BYTES // 1024} KB mesmo com DPI baixo")


def _weighted(df: pd.DataFrame, col: str) -> pd.Series:
    """Média por semana ponderada pela população (incidência do Brasil a partir das UFs)."""
    w = df["population"]
    return (df[col] * w).groupby(df["target_date"]).sum() / w.groupby(df["target_date"]).sum()


def _test(pred: pd.DataFrame) -> pd.DataFrame:
    t = pred[pred["split"] == "test"].copy()
    t["target_date"] = pd.to_datetime(t["target_date"])
    return t


def forecast_vs_observed(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    t = _test(pred)
    obs, prev = _weighted(t, "y_true"), _weighted(t, "y_pred")
    plt = _plt()
    fig, ax = plt.subplots()
    ax.plot(obs.index, obs.values, color=CINZA, lw=2, label="Observado")
    ax.plot(prev.index, prev.values, color=AZUL, lw=2, label="Previsto")
    ax.set_title(f"{model.name}: previsto × observado no Brasil (teste, {len(obs)} semanas)")
    ax.set_ylabel("Casos por 100 mil habitantes")
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    _save(fig, path)
    plt.close(fig)


def error_by_uf(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    t = by_uf[by_uf["split"] == "test"].sort_values("nrmse")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, max(4.5, 0.22 * len(t))))
    ax.barh(t["uf"], t["nrmse"], color=AZUL)
    ax.set_title(f"{model.name}: erro por UF no teste (NRMSE)")
    ax.set_xlabel("NRMSE (menor é melhor)")
    ax.grid(axis="y", visible=False)
    _save(fig, path)
    plt.close(fig)


def feature_importance(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    inner = model.model
    if hasattr(inner, "get_feature_importance"):  # CatBoost
        values, names = inner.get_feature_importance(), list(inner.feature_names_)
    else:  # Ensemble: RandomForest com as colunas p_<base> e poly<grau>
        values = inner.feature_importances_
        names = [f"previsão {b}" for b in model.bases] + [f"extrapolação grau {d}" for d in (0, 1, 2)]
    order = np.argsort(values)[-15:]
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.3 * len(order))))
    ax.barh([names[i] for i in order], np.asarray(values)[order], color=AZUL)
    ax.set_title(f"{model.name}: importância das variáveis")
    ax.set_xlabel("Importância relativa")
    ax.grid(axis="y", visible=False)
    _save(fig, path)
    plt.close(fig)


def learning_curve(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    curve = list(model.val_curve)
    if not curve:
        raise ValueError("sem curva de validação (treino sem validação)")
    plt = _plt()
    fig, ax = plt.subplots()
    ax.plot(range(1, len(curve) + 1), curve, color=AZUL, lw=2, label="Erro de validação (MSE)")
    if model.best_epoch:
        ax.axvline(model.best_epoch, color=ROSA, ls="--", label=f"Melhor época ({model.best_epoch})")
    ax.set_title("LSTM: curva de aprendizado")
    ax.set_xlabel("Época")
    ax.set_ylabel("Erro de validação (escala padronizada)")
    ax.legend(frameon=False)
    _save(fig, path)
    plt.close(fig)


def error_by_week(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    t = _test(pred)
    t["abs_err"] = (t["y_pred"] - t["y_true"]).abs()
    err = _weighted(t, "abs_err")
    plt = _plt()
    fig, ax = plt.subplots()
    ax.fill_between(err.index, err.values, color=AZUL, alpha=0.25)
    ax.plot(err.index, err.values, color=AZUL, lw=2)
    ax.set_title(f"{model.name}: erro absoluto por semana (teste)")
    ax.set_ylabel("Erro absoluto (casos por 100 mil)")
    fig.autofmt_xdate()
    _save(fig, path)
    plt.close(fig)


def posterior(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    p = model._draws()
    plt = _plt()
    fig, axes = plt.subplots(1, 3, figsize=(9, 3.6))
    for ax, (key, title) in zip(
        axes, (("a", "Nível geral"), ("beta", "Peso da semana anterior"), ("alpha", "Dispersão")), strict=True
    ):
        values = np.asarray(p[key]).ravel()
        ax.hist(values, bins=30, color=AZUL, alpha=0.8)
        ax.axvline(float(np.median(values)), color=ROSA, lw=2)
        ax.set_title(title)
        ax.set_yticks([])
    fig.suptitle("Baseline bayesiano: distribuição posterior (linha = mediana)")
    _save(fig, path)
    plt.close(fig)


def interval_coverage(model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, path: Path) -> None:
    t = _test(pred).dropna(subset=["lower", "upper"])
    if t.empty:
        raise ValueError("sem intervalo previsto")
    inside = ((t["y_true"] >= t["lower"]) & (t["y_true"] <= t["upper"])).groupby(t["uf"]).mean().sort_values()
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, max(4.5, 0.22 * len(inside))))
    ax.barh(inside.index, inside.values * 100, color=AZUL)
    ax.axvline(80, color=ROSA, ls="--", label="Nível do intervalo (80%)")
    ax.set_title(f"{model.name}: cobertura do intervalo no teste")
    ax.set_xlabel("% dos observados dentro do intervalo")
    ax.set_xlim(0, 100)
    ax.legend(frameon=False)
    ax.grid(axis="y", visible=False)
    _save(fig, path)
    plt.close(fig)


FUNCTIONS: dict[str, Callable[..., None]] = {
    "forecast_vs_observed.png": forecast_vs_observed,
    "error_by_uf.png": error_by_uf,
    "feature_importance.png": feature_importance,
    "learning_curve.png": learning_curve,
    "error_by_week.png": error_by_week,
    "posterior.png": posterior,
    "interval_coverage.png": interval_coverage,
}


def planned(model: Any) -> dict[str, str]:
    """Nome do arquivo → legenda das figuras previstas para o modelo (comuns + da família)."""
    out = dict(COMMON)
    if model.family in FAMILY:
        name, caption = FAMILY[model.family]
        out[name] = caption
    return out


def make_figures(
    model: Any, pred: pd.DataFrame, by_uf: pd.DataFrame, out_dir: Path
) -> tuple[dict[str, str], list[str]]:
    """Gera as figuras do modelo em `out_dir`. Devolve (legendas das geradas, nomes que falharam)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    done: dict[str, str] = {}
    failed: list[str] = []
    for name, caption in planned(model).items():
        path = out_dir / name
        try:
            FUNCTIONS[name](model, pred, by_uf, path)
            done[name] = caption
        except Exception:  # noqa: BLE001 — uma figura quebrada nunca derruba a run
            path.unlink(missing_ok=True)
            failed.append(name)
    (out_dir / CAPTIONS).write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    return done, failed
