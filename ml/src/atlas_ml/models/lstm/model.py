"""LSTM em PyTorch com embedding de UF (README.md desta pasta)."""

from __future__ import annotations

import copy

import mlflow
import numpy as np
import pandas as pd
import torch
from torch import nn

from atlas_ml.forecast.config import ForecastConfig
from atlas_ml.forecast.windows import Batch, augment


def _tensors(batch: Batch):
    """(seq, uf, extra, y): seq = histórico (+ covariáveis por passo), extra = sazonalidade."""
    n, w = batch.hist.shape
    steps = [batch.hist[:, :, None]]
    if batch.features.shape[1]:
        k = batch.features.shape[1] // w
        steps.append(batch.features.reshape(n, k, w).transpose(0, 2, 1))
    seq = np.concatenate(steps, axis=2).astype("float32")
    return (
        torch.from_numpy(seq),
        torch.from_numpy(batch.meta["uf_code"].to_numpy(dtype="int64").copy()),
        torch.from_numpy(batch.season.astype("float32")),
        torch.from_numpy(batch.y.astype("float32")),
    )


class Net(nn.Module):
    """Embedding(UF) concatenado a cada passo → LSTM(h1) → LSTM(h2) → [h, sazonalidade] → Linear."""

    def __init__(self, n_ufs: int, n_inputs: int, emb: int, h1: int, h2: int, dropout: float):
        super().__init__()
        self.emb = nn.Embedding(n_ufs, emb)
        self.lstm1 = nn.LSTM(n_inputs + emb, h1, batch_first=True)
        self.lstm2 = nn.LSTM(h1, h2, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(h2 + 2, 1)

    def forward(self, seq, uf, season):
        e = self.emb(uf).unsqueeze(1).expand(-1, seq.shape[1], -1)
        x, _ = self.lstm1(torch.cat([seq, e], dim=2))
        x, _ = self.lstm2(self.drop(x))
        last = self.drop(x[:, -1, :])
        return self.head(torch.cat([last, season], dim=1)).squeeze(1)


class LSTMForecast:
    name = "lstm"
    family = "rnn"
    supports_oof = True

    def __init__(
        self,
        cfg: ForecastConfig,
        n_ufs: int = 27,
        emb: int = 4,
        hidden1: int = 60,
        hidden2: int = 20,
        dropout: float = 0.5,
        lr: float = 1e-3,
        batch_size: int = 64,
        max_epochs: int = 200,
        patience: int = 12,
    ):
        self.cfg = cfg
        self.hp = {
            "n_ufs": n_ufs,
            "emb": emb,
            "hidden1": hidden1,
            "hidden2": hidden2,
            "dropout": dropout,
            "lr": lr,
            "batch_size": batch_size,
            "max_epochs": max_epochs,
            "patience": patience,
        }
        self.net = None
        self.best_epoch: int | None = None
        self.epochs_run = 0
        self.val_curve: list[float] = []  # erro de validação por época (figura de aprendizado)

    def fit(self, train: Batch, val: Batch) -> None:
        torch.manual_seed(self.cfg.seed)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(max(1, torch.get_num_threads()))
        rng = np.random.default_rng(self.cfg.seed)
        n_ufs = max(self.hp["n_ufs"], int(train.meta["uf_code"].max()) + 1)
        aug = augment(train, self.cfg, rng)  # aumento só no treino
        seq, uf, season, y = _tensors(aug)
        self.net = Net(
            n_ufs, seq.shape[2], self.hp["emb"], self.hp["hidden1"], self.hp["hidden2"], self.hp["dropout"]
        )
        # Adam com o lr configurado de fato (o original criava o otimizador e não o usava)
        opt = torch.optim.Adam(self.net.parameters(), lr=self.hp["lr"])
        loss_fn = torch.nn.MSELoss()
        val_t = _tensors(val) if len(val) else None
        gen = torch.Generator().manual_seed(self.cfg.seed)
        best, best_state, wait = float("inf"), None, 0
        for epoch in range(self.hp["max_epochs"]):
            self.net.train()
            perm = torch.randperm(len(y), generator=gen)
            for i in range(0, len(y), self.hp["batch_size"]):
                idx = perm[i : i + self.hp["batch_size"]]
                opt.zero_grad()
                loss = loss_fn(self.net(seq[idx], uf[idx], season[idx]), y[idx])
                loss.backward()
                opt.step()
            self.epochs_run = epoch + 1
            if val_t is None:
                continue
            # early stopping só na validação, restaurando os melhores pesos
            self.net.eval()
            with torch.no_grad():
                v = float(loss_fn(self.net(*val_t[:3]), val_t[3]))
            self.val_curve.append(v)
            if v < best - 1e-6:
                best, best_state, wait, self.best_epoch = (
                    v,
                    copy.deepcopy(self.net.state_dict()),
                    0,
                    epoch + 1,
                )
            else:
                wait += 1
                if wait >= self.hp["patience"]:
                    break
        if best_state is not None:
            self.net.load_state_dict(best_state)
        self.net.eval()

    def predict(self, batch: Batch) -> pd.DataFrame:
        seq, uf, season, _ = _tensors(batch)
        with torch.no_grad():
            z = self.net(seq, uf, season).numpy()
        return pd.DataFrame({"y_pred": batch.to_incidence(z)})

    def params(self) -> dict[str, object]:
        return {**self.hp, "best_epoch": self.best_epoch, "epochs_run": self.epochs_run}

    def log_model(self, example: Batch) -> str:
        # pickle: o forward tem 3 entradas (seq, uf_code, season), que o formato pt2 não descreve
        # na assinatura; a rede fica no nível do módulo, então o pickle a reconstrói
        info = mlflow.pytorch.log_model(self.net, name="model", serialization_format="pickle")
        # contrato de entrada e escala, para quem for servir o modelo
        sc = example.scaler
        mlflow.log_dict(
            {
                "forward": "seq[n, window, 1 + k] float32, uf_code[n] int64, season[n, 2] float32 -> z[n]",
                "seq": "log1p(incidência) padronizada: (x - mean) / std",
                "output": "incidência = max(expm1(z * std + mean), 0)",
                "mean": sc.mean,
                "std": sc.std,
                "window": self.cfg.window,
                "horizon": self.cfg.horizon,
                "features": list(self.cfg.features),
            },
            "model_extra/input_contract.json",
        )
        return info.model_uri


def build(cfg: ForecastConfig, **kwargs) -> LSTMForecast:
    return LSTMForecast(cfg, **kwargs)
