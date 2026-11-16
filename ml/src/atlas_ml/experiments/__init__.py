"""Experimentos disponíveis em `atlas-ml train <nome>`."""

from atlas_ml.experiments.example import run_example

EXPERIMENTS = {"example": run_example}

__all__ = ["EXPERIMENTS"]
