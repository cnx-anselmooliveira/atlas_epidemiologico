"""Fonte única das células `comum` dos notebooks de modelo (ferramenta de desenvolvimento).

Os seis notebooks são autocontidos: cada um carrega estas células, escritas no próprio arquivo, e
roda sem este módulo. Aqui fica só a fonte para manter as cópias idênticas: `sincronizar_comum.py`
reescreve as células nos notebooks e `verificar_comum.py` (CI) falha se alguma divergir.

Cada entrada de CELULAS é o código de uma célula, identificada pelo nome da seção (metadado `secao`
da célula). ORDEM é a ordem em que as seções aparecem no notebook (a seção do modelo fica entre
`janelas_montar` e `avaliacao_funcoes`).
"""

ORDEM = [
    "ambiente",
    "dados_funcoes",
    "dados_ler",
    "janelas_config",
    "janelas_funcoes",
    "janelas_escala",
    "janelas_montar",
    # --- aqui entra a seção do modelo (definição e treino), exclusiva de cada notebook ---
    "avaliacao_funcoes",
    "avaliacao",
    "oof_funcoes",
    "oof",
    "futuro_funcoes",
    "futuro",
    "figuras_funcoes",
    "registro",
    "resultado",
]

# Seções que vêm antes e depois da seção do modelo
ANTES_DO_MODELO = ORDEM[: ORDEM.index("janelas_montar") + 1]
DEPOIS_DO_MODELO = ORDEM[ORDEM.index("janelas_montar") + 1 :]

CELULAS: dict[str, str] = {}

# --------------------------------------------------------------------------------------------
CELULAS["ambiente"] = """\
# Ambiente: threads, configuração do projeto, MLflow e versão do notebook
import os


def threads():
    # threads por tarefa de treino: ATLAS_THREADS, ou um terço dos núcleos (no mínimo 1)
    pedido = os.environ.get("ATLAS_THREADS", "").strip()
    if pedido.isdigit() and int(pedido) > 0:
        return int(pedido)
    return max(1, (os.cpu_count() or 3) // 3)


# antes de importar numpy, PyTorch, CatBoost e afins: várias tarefas rodam juntas na mesma máquina
for _nome in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_nome, str(threads()))
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

import hashlib
import importlib.metadata as md
import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

# ajudantes de plataforma (não são código de modelo): configuração, tags atlas.* e registro
from atlas_ml.config import load_settings
from atlas_ml.registry import register_model
from atlas_ml.tracking import atlas_run

print("Pacotes deste notebook (requirements.txt):")
for _pacote in PACOTES:
    try:
        print(f"  {_pacote:26s} {md.version(_pacote)}")
    except md.PackageNotFoundError:
        print(f"  {_pacote:26s} NÃO INSTALADO")

settings = load_settings()
_ = settings.git_sha  # falha cedo se o commit da imagem não estiver definido
mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
EXPERIMENT = os.environ.get("ATLAS_FORECAST_EXPERIMENT", "dengue-forecast-br")  # atlas/<EXPERIMENT>


def versao_do_notebook():
    # SHA da árvore que o git-sync clonou (o link aponta para .worktrees/<sha>); fora do clone: local
    if os.environ.get("ATLAS_NOTEBOOK_SHA"):
        return os.environ["ATLAS_NOTEBOOK_SHA"]
    link = os.environ.get("ATLAS_DAGS_LINK")
    if link and os.path.islink(link):
        return os.path.basename(os.readlink(link).rstrip("/\\\\")) or "local"
    return "local"


os.environ["ATLAS_NOTEBOOK_SHA"] = versao_do_notebook()  # vira a tag atlas.notebook_sha da run
trabalho = Path(tempfile.mkdtemp(prefix="atlas-notebook-"))  # artefatos da run até o registro
print(
    f"ambiente={settings.atlas_env}  mlflow={settings.mlflow_tracking_uri}  experimento=atlas/{EXPERIMENT}  "
    f"commit={settings.git_sha}  notebook={os.environ['ATLAS_NOTEBOOK_SHA']}  threads={threads()}"
)
"""

# --------------------------------------------------------------------------------------------
CELULAS["dados_funcoes"] = '''\
# Dados: a gold de casos prováveis por UF e semana → painel UF × semana
PROJETO = "ppgcc-dengue-project"
CANAIS = (
    "notified_cases",
    "discarded_cases",
    "confirmed_cases",
    "alarm_cases",
    "severe_cases",
    "inconclusive_cases",
    "investigation_cases",
    "deaths",
)
ESTATICAS = ("mean_elevation_m", "mean_slope_deg")
FEATURES_PADRAO = CANAIS + ESTATICAS
COLUNAS_PAINEL = [
    "uf", "uf_code", "week_start", "year", "epi_week", "cases", "population", "incidence", "filled",
    *CANAIS, *ESTATICAS,
]


def tabela_gold(env):
    # gold em dev; gold_hml e gold_prod nos outros ambientes (mesma regra do dbt e do Airflow)
    env = (env or "").strip().lower()
    if env not in ("dev", "hml", "prod"):
        raise ValueError(f"Ambiente inválido: {env!r} (use dev, hml ou prod)")
    dataset = "gold" if env == "dev" else f"gold_{env}"
    return f"{PROJETO}.{dataset}.gold_dengue_casos_provaveis_uf_semanal"


def consulta(tabela):
    if not re.fullmatch(r"[A-Za-z0-9_-]+\\.[A-Za-z0-9_]+\\.[A-Za-z0-9_]+", tabela):
        raise ValueError(f"Tabela de origem inválida: {tabela!r} (use projeto.dataset.tabela)")
    return f"""
SELECT uf, week_start, epi_year AS year, epi_week, probable_cases AS cases, population,
       {", ".join(CANAIS)},
       {", ".join(ESTATICAS)}
FROM `{tabela}`
"""


def montar_painel(raw):
    # painel regular: semanas faltantes viram zero (filled=True), incidência por 100 mil, uf_code estável
    df = raw.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    sem_canal = [c for c in CANAIS if c not in df]
    if sem_canal:
        raise ValueError(f"A gold não trouxe os canais: {', '.join(sem_canal)}")
    for col in ESTATICAS:
        if col not in df:
            df[col] = float("nan")
    sem_populacao = sorted(df.loc[df["population"].isna(), "uf"].unique())
    if sem_populacao:
        raise ValueError(f"UFs sem população na gold: {', '.join(sem_populacao)}")
    if df.duplicated(["uf", "week_start"]).any():
        raise ValueError("A consulta retornou mais de uma linha por UF e semana.")
    quadros = []
    for uf, g in df.groupby("uf", sort=True):
        g = g.set_index("week_start").sort_index()
        completa = pd.date_range(g.index.min(), g.index.max(), freq="7D")
        g = g.reindex(completa)
        g.index.name = "week_start"
        g["filled"] = g["cases"].isna()
        g["uf"] = uf
        g["cases"] = g["cases"].fillna(0).astype("int64")
        for col in CANAIS:
            g[col] = g[col].fillna(0).astype("int64")
        g["population"] = g["population"].ffill().bfill()
        for col in ESTATICAS:
            g[col] = g[col].ffill().bfill()
        iso = g.index.isocalendar()
        g["year"] = g["year"].fillna(pd.Series(iso.year.values, index=g.index)).astype("int64")
        g["epi_week"] = g["epi_week"].fillna(pd.Series(iso.week.values, index=g.index)).astype("int64")
        quadros.append(g.reset_index())
    painel = pd.concat(quadros, ignore_index=True)
    codigos = {uf: i for i, uf in enumerate(sorted(painel["uf"].unique()))}
    painel["uf_code"] = painel["uf"].map(codigos).astype("int64")
    painel["population"] = painel["population"].astype("float64")
    for col in ESTATICAS:
        painel[col] = painel[col].astype("float64")
    painel["incidence"] = painel["cases"] / painel["population"] * 1e5
    return painel[COLUNAS_PAINEL].sort_values(["uf", "week_start"]).reset_index(drop=True)
'''

# --------------------------------------------------------------------------------------------
CELULAS["dados_ler"] = """\
# Dados: leitura (BigQuery, ou um painel salvo em parquet) e versão da gold
def ler_painel():
    if painel_parquet:
        arquivo = Path(painel_parquet)
        painel = pd.read_parquet(arquivo)
        faltam = [c for c in COLUNAS_PAINEL if c not in painel.columns]
        if faltam:
            raise ValueError(f"O painel {arquivo.name} não tem as colunas: {', '.join(faltam)}")
        painel["week_start"] = pd.to_datetime(painel["week_start"])
        versao = "parquet:" + hashlib.sha1(arquivo.read_bytes()).hexdigest()[:12]
        return painel[COLUNAS_PAINEL], versao, str(arquivo)
    from google.cloud import bigquery

    tabela = fonte or tabela_gold(settings.atlas_env)
    cliente = bigquery.Client(project=settings.gcp_project)
    sql = consulta(tabela)
    modificada = cliente.get_table(tabela).modified  # a versão da gold: muda a cada reconstrução do dbt
    bruto = cliente.query(sql).to_dataframe()
    versao = f"query:{hashlib.sha1(sql.encode()).hexdigest()[:12]}+{tabela}@{modificada.isoformat()}"
    return montar_painel(bruto), versao, tabela


painel_bruto, data_version, origem_dos_dados = ler_painel()
if data_version_esperada and data_version_esperada not in data_version:
    raise RuntimeError(
        f"A gold mudou desde o início da execução: esperada {data_version_esperada!r}, agora {data_version!r}. "
        "Dispare de novo para todos os modelos usarem a mesma versão."
    )
print(f"origem: {origem_dos_dados}")
print(f"versão dos dados: {data_version}")
print(
    f"painel: {len(painel_bruto)} linhas, {painel_bruto['uf'].nunique()} UFs, "
    f"{painel_bruto['week_start'].min().date()} a {painel_bruto['week_start'].max().date()}, "
    f"{int(painel_bruto['filled'].sum())} semanas preenchidas"
)
"""

# --------------------------------------------------------------------------------------------
CELULAS["janelas_config"] = """\
# Janelas e divisão: configuração, cortes por data do alvo e blocos out-of-fold
MAX_HORIZON = 4  # o site mostra as próximas 4 semanas


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
    features: tuple = FEATURES_PADRAO  # covariáveis do painel que entram em cada passo da janela

    def __post_init__(self):
        if self.window < 1 or self.horizon < 1:
            raise ValueError("window e horizon devem ser >= 1")
        if self.horizon > MAX_HORIZON:
            raise ValueError(f"horizon deve ser de 1 a {MAX_HORIZON} semanas")
        if self.test_weeks < 1 or self.val_weeks < 1:
            raise ValueError("test_weeks e val_weeks devem ser >= 1")

    def as_params(self):
        params = dict(self.__dict__)
        params["features"] = ",".join(self.features) or "-"
        return params


if not str(features).strip():  # vazio = canais do SINAN + relevo; "-" = só a incidência
    cfg = ForecastConfig(window=int(window), horizon=int(horizon), seed=int(seed))
else:
    _lista = tuple(f.strip() for f in str(features).split(",") if f.strip() and f.strip() != "-")
    cfg = ForecastConfig(window=int(window), horizon=int(horizon), seed=int(seed), features=_lista)

TRAIN, VAL, TEST = "train", "val", "test"
FUTURE = "future"  # janelas sem alvo (previsão das próximas semanas)


@dataclass(frozen=True)
class SplitDates:
    # alvo >= test_start → teste; val_start <= alvo < test_start → validação; antes disso, treino
    val_start: pd.Timestamp
    test_start: pd.Timestamp

    def assign(self, target_dates):
        d = pd.to_datetime(pd.Series(target_dates)).to_numpy()
        out = np.full(len(d), TRAIN, dtype=object)
        out[d >= self.val_start.to_datetime64()] = VAL
        out[d >= self.test_start.to_datetime64()] = TEST
        return out


def split_dates(all_dates, cfg):
    weeks = pd.DatetimeIndex(pd.to_datetime(pd.Series(all_dates)).unique()).sort_values()
    needed = cfg.test_weeks + cfg.val_weeks + cfg.window + cfg.horizon
    if len(weeks) < needed:
        raise ValueError(f"Período curto demais: {len(weeks)} semanas, mínimo {needed}.")
    test_start = weeks[-cfg.test_weeks]
    val_start = weeks[-(cfg.test_weeks + cfg.val_weeks)]
    return SplitDates(val_start=val_start, test_start=test_start)


def oof_blocks(train_target_dates, cfg):
    # blocos finais do treino, em ordem cronológica [(início, fim_exclusivo), ...]: rolling origin
    weeks = pd.DatetimeIndex(pd.to_datetime(pd.Series(train_target_dates)).unique()).sort_values()
    total = cfg.oof_folds * cfg.oof_block_weeks
    if len(weeks) <= total:
        raise ValueError(f"Treino curto demais para {cfg.oof_folds} blocos OOF de {cfg.oof_block_weeks} semanas.")
    blocks = []
    for k in range(cfg.oof_folds, 0, -1):
        start = weeks[len(weeks) - k * cfg.oof_block_weeks]
        end_idx = len(weeks) - (k - 1) * cfg.oof_block_weeks
        end = weeks[end_idx] if end_idx < len(weeks) else weeks[-1] + pd.Timedelta(days=1)
        blocks.append((start, end))
    return blocks
"""

# --------------------------------------------------------------------------------------------
CELULAS["janelas_funcoes"] = """\
# Janelas N → H por UF: histórico até a origem t e alvo na semana t + horizon (nada depois da origem)
def drop_immature(panel, cfg):
    # descarta as últimas semanas: o atraso de notificação as deixa subestimadas
    if cfg.drop_recent_weeks <= 0:
        return panel
    weeks = np.sort(panel["week_start"].unique())
    cut = weeks[-cfg.drop_recent_weeks]
    return panel[panel["week_start"] < cut].reset_index(drop=True)


def feature_values(g, name):
    # canal epidemiológico (contagem) → log1p(taxa por 100 mil); qualquer outra coluna entra como está
    x = g[name].to_numpy(dtype="float64")
    if name in CANAIS:
        return np.log1p(x / g["population"].to_numpy(dtype="float64") * 1e5)
    return x


@dataclass
class RawWindows:
    meta: pd.DataFrame  # uf, uf_code, origin_date, target_date, population, y_true (+ split)
    hist: np.ndarray  # (n, window) log1p(incidência)
    target: np.ndarray  # (n,) log1p(incidência) no alvo
    season: np.ndarray  # (n, 2) sin/cos da semana do ano do alvo
    features: np.ndarray  # (n, window * len(cfg.features)) covariáveis, sem escala
    feature_names: list

    def subset(self, mask):
        return RawWindows(
            meta=self.meta[mask].reset_index(drop=True),
            hist=self.hist[mask],
            target=self.target[mask],
            season=self.season[mask],
            features=self.features[mask],
            feature_names=self.feature_names,
        )

    def __len__(self):
        return len(self.meta)


def build_windows(panel, cfg):
    faltam = [f for f in cfg.features if f not in panel.columns]
    if faltam:
        raise ValueError(f"Covariáveis ausentes no painel: {', '.join(faltam)}")
    metas, hists, targets, seasons, feats = [], [], [], [], []
    w, h = cfg.window, cfg.horizon
    for _, g in panel.sort_values(["uf", "week_start"]).groupby("uf", sort=True):
        z = np.log1p(g["incidence"].to_numpy(dtype="float64"))
        dates = g["week_start"].to_numpy()
        n = len(g) - w - h + 1
        if n <= 0:
            continue
        idx = np.arange(n)[:, None] + np.arange(w)[None, :]  # (n, w)
        origin = idx[:, -1]
        tgt = origin + h
        hists.append(z[idx])
        targets.append(z[tgt])
        target_dates = pd.DatetimeIndex(dates[tgt])
        angle = 2 * np.pi * (target_dates.isocalendar().week.to_numpy(dtype="float64") - 1) / 52.0
        seasons.append(np.column_stack([np.sin(angle), np.cos(angle)]))
        if cfg.features:
            # idx vai só até a origem: nenhum canal da semana-alvo (t+h) entra na janela
            cols = [feature_values(g, f)[idx] for f in cfg.features]
            feats.append(np.concatenate(cols, axis=1))
        else:
            feats.append(np.empty((n, 0)))
        metas.append(
            pd.DataFrame(
                {
                    "uf": g["uf"].iloc[0],
                    "uf_code": int(g["uf_code"].iloc[0]),
                    "origin_date": dates[origin],
                    "target_date": dates[tgt],
                    "population": g["population"].to_numpy()[tgt],
                    "y_true": g["incidence"].to_numpy(dtype="float64")[tgt],
                }
            )
        )
    if not metas:
        raise ValueError("Nenhuma janela: séries curtas demais para window + horizon.")
    names = [f"{f}_t-{w - 1 - k}" for f in cfg.features for k in range(w)]
    return RawWindows(
        meta=pd.concat(metas, ignore_index=True),
        hist=np.concatenate(hists),
        target=np.concatenate(targets),
        season=np.concatenate(seasons),
        features=np.concatenate(feats),
        feature_names=names,
    )


def build_future_windows(panel, cfg):
    # uma janela por UF terminando na última semana madura, com alvo em origem + horizonte (sem y_true)
    faltam = [f for f in cfg.features if f not in panel.columns]
    if faltam:
        raise ValueError(f"Covariáveis ausentes no painel: {', '.join(faltam)}")
    w = cfg.window
    metas, hists, seasons, feats = [], [], [], []
    for _, g in panel.sort_values(["uf", "week_start"]).groupby("uf", sort=True):
        if len(g) < w:
            continue
        tail = g.iloc[-w:]
        origin = pd.Timestamp(tail["week_start"].iloc[-1])
        target = origin + pd.Timedelta(weeks=cfg.horizon)
        hists.append(np.log1p(tail["incidence"].to_numpy(dtype="float64"))[None, :])
        angle = 2 * np.pi * (target.isocalendar().week - 1) / 52.0
        seasons.append(np.array([[np.sin(angle), np.cos(angle)]]))
        if cfg.features:
            feats.append(np.concatenate([feature_values(tail, f) for f in cfg.features])[None, :])
        else:
            feats.append(np.empty((1, 0)))
        metas.append(
            pd.DataFrame(
                {
                    "uf": [g["uf"].iloc[0]],
                    "uf_code": [int(g["uf_code"].iloc[0])],
                    "origin_date": [origin],
                    "target_date": [target],
                    "population": [float(tail["population"].iloc[-1])],
                    "y_true": [np.nan],
                    "split": [FUTURE],
                }
            )
        )
    if not metas:
        raise ValueError("Nenhuma UF com histórico suficiente para a janela do futuro.")
    return RawWindows(
        meta=pd.concat(metas, ignore_index=True),
        hist=np.concatenate(hists),
        target=np.full(len(metas), np.nan),
        season=np.concatenate(seasons),
        features=np.concatenate(feats),
        feature_names=[f"{f}_t-{w - 1 - k}" for f in cfg.features for k in range(w)],
    )


def assign_splits(raw, cfg):
    datas = split_dates(raw.meta["target_date"], cfg)
    raw.meta["split"] = datas.assign(raw.meta["target_date"])
    return datas
"""

# --------------------------------------------------------------------------------------------
CELULAS["janelas_escala"] = """\
# Escala e lotes: o escalonador é ajustado só no treino; validação e teste só recebem a transformação
@dataclass(frozen=True)
class TrainOnlyScaler:
    mean: float  # média e desvio de log1p(incidência) (histórico e alvo compartilham a escala)
    std: float
    feat_mean: np.ndarray  # uma média e um desvio por covariável
    feat_std: np.ndarray
    n_features: int

    @classmethod
    def fit(cls, train, n_features):
        values = np.concatenate([train.hist.ravel(), train.target])
        std = float(values.std()) or 1.0
        if train.features.shape[1]:
            f = train.features.reshape(len(train), n_features, -1)
            fm = f.mean(axis=(0, 2))
            fs = f.std(axis=(0, 2))
            fs[fs == 0] = 1.0
        else:
            fm, fs = np.zeros(0), np.ones(0)
        return cls(float(values.mean()), std, fm, fs, n_features)

    def z(self, x):
        return (x - self.mean) / self.std

    def inverse(self, z):
        # escala padronizada → incidência (expm1), nunca negativa
        return np.clip(np.expm1(np.asarray(z) * self.std + self.mean), 0.0, None)

    def features(self, f):
        if not self.n_features:
            return f
        n = len(f)
        r = f.reshape(n, self.n_features, -1)
        return ((r - self.feat_mean[None, :, None]) / self.feat_std[None, :, None]).reshape(n, -1)


@dataclass
class Batch:
    # entrada dos modelos: tudo padronizado pelo escalonador do treino
    meta: pd.DataFrame
    hist: np.ndarray  # (n, window)
    season: np.ndarray  # (n, 2)
    features: np.ndarray  # (n, window * k)
    y: np.ndarray  # (n,) alvo padronizado
    scaler: TrainOnlyScaler
    feature_names: list

    def __len__(self):
        return len(self.meta)

    def tabular(self, with_uf=True):
        # [histórico, sin, cos, covariáveis, (uf_code)] — entrada de CatBoost e SVR
        parts = [self.hist, self.season, self.features]
        if with_uf:
            parts.append(self.meta["uf_code"].to_numpy(dtype="float64")[:, None])
        return np.concatenate(parts, axis=1)

    def tabular_names(self, with_uf=True):
        w = self.hist.shape[1]
        names = [f"inc_t-{w - 1 - k}" for k in range(w)] + ["season_sin", "season_cos"]
        names += self.feature_names
        return names + (["uf_code"] if with_uf else [])

    def to_incidence(self, z):
        return self.scaler.inverse(z)


def make_batch(raw, scaler):
    return Batch(
        meta=raw.meta.reset_index(drop=True),
        hist=scaler.z(raw.hist),
        season=raw.season,
        features=scaler.features(raw.features),
        y=scaler.z(raw.target),
        scaler=scaler,
        feature_names=raw.feature_names,
    )


@dataclass
class Prepared:
    train: Batch
    val: Batch
    test: Batch
    scaler: TrainOnlyScaler


def prepare_batches(raw, cfg):
    split = raw.meta["split"].to_numpy()
    train = raw.subset(split == TRAIN)
    scaler = TrainOnlyScaler.fit(train, len(cfg.features))
    return Prepared(
        train=make_batch(train, scaler),
        val=make_batch(raw.subset(split == VAL), scaler),
        test=make_batch(raw.subset(split == TEST), scaler),
        scaler=scaler,
    )


def augment(batch, cfg, rng):
    # cópias com ruído gaussiano no histórico padronizado (só para o treino)
    if cfg.augment <= 0:
        return batch
    copies = [batch.hist] + [
        batch.hist + rng.normal(0.0, cfg.augment_sigma, batch.hist.shape) for _ in range(cfg.augment)
    ]
    k = cfg.augment + 1
    return Batch(
        meta=pd.concat([batch.meta] * k, ignore_index=True),
        hist=np.concatenate(copies),
        season=np.tile(batch.season, (k, 1)),
        features=np.tile(batch.features, (k, 1)),
        y=np.tile(batch.y, k),
        scaler=batch.scaler,
        feature_names=batch.feature_names,
    )
"""

# --------------------------------------------------------------------------------------------
CELULAS["janelas_montar"] = """\
# Janelas e divisão: descarta as semanas imaturas, monta as janelas e padroniza só com o treino
painel = drop_immature(painel_bruto, cfg)
raw = build_windows(painel, cfg)
datas = assign_splits(raw, cfg)
prep = prepare_batches(raw, cfg)
print(f"semanas imaturas descartadas: {cfg.drop_recent_weeks}  (painel até {painel['week_start'].max().date()})")
print(f"cortes: validação a partir de {datas.val_start.date()}, teste a partir de {datas.test_start.date()}")
print(f"janelas: treino={len(prep.train)}  validação={len(prep.val)}  teste={len(prep.test)}")
print(
    f"entrada tabular: {prep.train.tabular().shape[1]} colunas "
    f"({cfg.window} semanas × {1 + len(cfg.features)} canais + sazonalidade + UF)"
)
print(f"configuração: {cfg.as_params()}")
"""

# --------------------------------------------------------------------------------------------
CELULAS["avaliacao_funcoes"] = """\
# Avaliação: métricas por UF (NRMSE = RMSE / amplitude observada da UF) e previsões na escala de incidência
METRICAS = ("nrmse", "mae", "rmse", "r2")


def _uf_metrics(y, p):
    err = p - y
    rmse = float(np.sqrt(np.mean(err**2)))
    span = float(y.max() - y.min())
    denom = span if span > 0 else (float(np.mean(np.abs(y))) or 1.0)
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = float(1 - np.sum(err**2) / ss_tot) if ss_tot > 0 else float("nan")
    return {"nrmse": rmse / denom, "mae": float(np.mean(np.abs(err))), "rmse": rmse, "r2": r2}


def metrics_by_uf(pred):
    rows = []
    for (split, uf), g in pred.groupby(["split", "uf"], sort=True):
        rows.append(
            {
                "split": split,
                "uf": uf,
                "n": len(g),
                **_uf_metrics(g["y_true"].to_numpy(float), g["y_pred"].to_numpy(float)),
            }
        )
    return pd.DataFrame(rows)


def summarize_metrics(by_uf):
    # médias entre UFs por split: <split>_<métrica>_mean (ex.: test_nrmse_mean)
    out = {}
    for split, g in by_uf.groupby("split"):
        for m in METRICAS:
            values = g[m].dropna()
            if len(values):
                out[f"{split}_{m}_mean"] = float(values.mean())
    return out


def interval_coverage(pred):
    # fração de observados dentro de [lower, upper], por split, quando há intervalo
    if not {"lower", "upper"} <= set(pred.columns) or pred["lower"].isna().all():
        return {}
    out = {}
    for split, g in pred.groupby("split"):
        inside = (g["y_true"] >= g["lower"]) & (g["y_true"] <= g["upper"])
        out[f"{split}_interval_coverage"] = float(inside.mean())
    return out


def predict_frame(modelo, batch, split):
    # previsões de um lote com a meta da janela; garante y_pred >= 0
    if not len(batch):
        return pd.DataFrame()
    out = modelo.predict(batch).reset_index(drop=True)
    df = batch.meta[["uf", "uf_code", "origin_date", "target_date", "population", "y_true"]].copy()
    df["split"] = split
    df["y_pred"] = np.clip(out["y_pred"].to_numpy(float), 0.0, None)
    for col in ("lower", "upper"):
        df[col] = np.clip(out[col].to_numpy(float), 0.0, None) if col in out else np.nan
    return df
"""

# --------------------------------------------------------------------------------------------
CELULAS["avaliacao"] = """\
# Avaliação: previsões de validação e teste, métricas por UF e médias
pred = pd.concat(
    [predict_frame(modelo, prep.val, VAL), predict_frame(modelo, prep.test, TEST)], ignore_index=True
)
pred["horizon"] = cfg.horizon
by_uf = metrics_by_uf(pred)
by_uf["horizon"] = cfg.horizon
metricas = {**summarize_metrics(by_uf), **interval_coverage(pred), "fit_seconds": fit_seconds}
print(f"previsões: {len(pred)} linhas ({(pred['split'] == VAL).sum()} de validação, {(pred['split'] == TEST).sum()} de teste)")
print(by_uf[by_uf["split"] == TEST][["uf", "n", *METRICAS]].round(4).to_string(index=False))
for _k, _v in metricas.items():
    print(f"  {_k:28s} {_v:.4f}")
"""

# --------------------------------------------------------------------------------------------
CELULAS["oof_funcoes"] = """\
# Out-of-fold: previsões do treino por blocos rolling origin, para o ensemble (só modelos-base)
OOF_INNER_VAL_WEEKS = 26  # validação interna (parada antecipada) dentro de cada bloco


def oof_predictions(raw, cfg):
    # para cada bloco, um modelo novo é ajustado só com alvos anteriores ao bloco (escalonador também)
    train_raw = raw.subset(raw.meta["split"].to_numpy() == TRAIN)
    target = train_raw.meta["target_date"]
    frames = []
    for fold, (start, end) in enumerate(oof_blocks(target, cfg)):
        fit_raw = train_raw.subset((target < start).to_numpy())
        weeks = np.sort(fit_raw.meta["target_date"].unique())
        inner = min(OOF_INNER_VAL_WEEKS, max(1, len(weeks) // 4))
        vcut = weeks[-inner]
        is_val = (fit_raw.meta["target_date"] >= vcut).to_numpy()
        scaler = TrainOnlyScaler.fit(fit_raw.subset(~is_val), len(cfg.features))
        m = criar_modelo()
        m.fit(make_batch(fit_raw.subset(~is_val), scaler), make_batch(fit_raw.subset(is_val), scaler))
        bloco = make_batch(train_raw.subset(((target >= start) & (target < end)).to_numpy()), scaler)
        df = predict_frame(m, bloco, "oof")
        df["fold"] = fold
        df["fit_until"] = start
        frames.append(df)
        print(f"  bloco {fold}: ajustado com alvos até {start.date()}, previu {len(df)} janelas")
    return pd.concat(frames, ignore_index=True)
"""

# --------------------------------------------------------------------------------------------
CELULAS["oof"] = """\
# Out-of-fold (modelos-base do ensemble: catboost, svr e lstm)
oof = None
if modelo.supports_oof:
    _t0 = time.perf_counter()
    print("previsões out-of-fold (rolling origin):")
    oof = oof_predictions(raw, cfg)
    metricas["oof_seconds"] = time.perf_counter() - _t0
    metricas.update(summarize_metrics(metrics_by_uf(oof)))  # oof_<métrica>_mean
    print(f"oof: {len(oof)} previsões, oof_nrmse_mean={metricas['oof_nrmse_mean']:.4f} ({metricas['oof_seconds']:.0f} s)")
else:
    print(f"{modelo.name} não gera previsões out-of-fold (fora do stacking).")
"""

# --------------------------------------------------------------------------------------------
CELULAS["futuro_funcoes"] = """\
# Futuro: a previsão das próximas semanas por UF, com a janela terminando na última semana madura
FUTURE_COLUMNS = ["uf", "origin_date", "target_date", "horizon", "y_pred", "lower", "upper"]


def predict_future(modelo, panel, cfg, scaler):
    batch = make_batch(build_future_windows(panel, cfg), scaler)
    df = predict_frame(modelo, batch, FUTURE)
    df["horizon"] = cfg.horizon
    return df[FUTURE_COLUMNS].reset_index(drop=True)
"""

# --------------------------------------------------------------------------------------------
CELULAS["futuro"] = """\
# Futuro: previsão do horizonte pedido para cada UF (sem alvo observado)
futuro = predict_future(modelo, painel, cfg, prep.scaler)
print(f"previsão futura: {len(futuro)} UFs, origem {futuro['origin_date'].max().date()} → alvo {futuro['target_date'].max().date()}")
print(futuro.head(5).round(3).to_string(index=False))
"""

# --------------------------------------------------------------------------------------------
CELULAS["figuras_funcoes"] = """\
# Figuras (PNG até 500 KB): duas comuns e uma da família do modelo; uma que falhe não derruba a run
MAX_BYTES = 500 * 1024
AZUL, CINZA, ROSA = "#016ca6", "#676b72", "#c0408a"


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


def _save(fig, path):
    # PNG com tamanho fixo: reduz o DPI se passar do limite e falha se ainda não couber
    for dpi in (100, 80, 60):
        fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        if path.stat().st_size <= MAX_BYTES:
            return
    raise ValueError(f"{path.name} passa de {MAX_BYTES // 1024} KB mesmo com DPI baixo")


def _weighted(df, col):
    # média por semana ponderada pela população (incidência do Brasil a partir das UFs)
    w = df["population"]
    return (df[col] * w).groupby(df["target_date"]).sum() / w.groupby(df["target_date"]).sum()


def _teste(pred):
    t = pred[pred["split"] == "test"].copy()
    t["target_date"] = pd.to_datetime(t["target_date"])
    return t


def fig_previsto_x_observado(modelo, pred, by_uf, path):
    t = _teste(pred)
    obs, prev = _weighted(t, "y_true"), _weighted(t, "y_pred")
    plt = _plt()
    fig, ax = plt.subplots()
    ax.plot(obs.index, obs.values, color=CINZA, lw=2, label="Observado")
    ax.plot(prev.index, prev.values, color=AZUL, lw=2, label="Previsto")
    ax.set_title(f"{modelo.name}: previsto × observado no Brasil (teste, {len(obs)} semanas)")
    ax.set_ylabel("Casos por 100 mil habitantes")
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    _save(fig, path)
    plt.close(fig)


def fig_erro_por_uf(modelo, pred, by_uf, path):
    t = by_uf[by_uf["split"] == "test"].sort_values("nrmse")
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, max(4.5, 0.22 * len(t))))
    ax.barh(t["uf"], t["nrmse"], color=AZUL)
    ax.set_title(f"{modelo.name}: erro por UF no teste (NRMSE)")
    ax.set_xlabel("NRMSE (menor é melhor)")
    ax.grid(axis="y", visible=False)
    _save(fig, path)
    plt.close(fig)


FIGURAS_COMUNS = {
    "forecast_vs_observed.png": (
        fig_previsto_x_observado,
        "Incidência semanal no Brasil no teste: observado × previsto pelo modelo.",
    ),
    "error_by_uf.png": (
        fig_erro_por_uf,
        "Erro de cada UF no teste (NRMSE: erro pela amplitude da série; menor é melhor).",
    ),
}


def gerar_figuras(modelo, pred, by_uf, pasta):
    # as figuras comuns mais a da família (o método `figura` do modelo, com figura_nome e figura_legenda)
    pasta.mkdir(parents=True, exist_ok=True)
    previstas = {nome: (fn, legenda) for nome, (fn, legenda) in FIGURAS_COMUNS.items()}
    if getattr(modelo, "figura_nome", None):
        previstas[modelo.figura_nome] = (modelo.figura, modelo.figura_legenda)
    feitas, falharam = {}, []
    for nome, (fn, legenda) in previstas.items():
        caminho = pasta / nome
        try:
            if fn in (fig_previsto_x_observado, fig_erro_por_uf):
                fn(modelo, pred, by_uf, caminho)
            else:
                fn(pred, by_uf, caminho)
            feitas[nome] = legenda
        except Exception as erro:  # uma figura quebrada nunca derruba a run
            caminho.unlink(missing_ok=True)
            falharam.append(nome)
            print(f"  figura {nome} falhou: {erro!r}")
    (pasta / "captions.json").write_text(json.dumps(feitas, ensure_ascii=False, indent=2), encoding="utf-8")
    return feitas, falharam


pasta_figuras = trabalho / "figures"
figuras_feitas, figuras_falharam = gerar_figuras(modelo, pred, by_uf, pasta_figuras)
print(f"figuras geradas: {sorted(figuras_feitas)}  falharam: {figuras_falharam or '-'}")
"""

# --------------------------------------------------------------------------------------------
CELULAS["registro"] = """\
# Registro no MLflow: tags atlas.*, parâmetros, métricas, artefatos, modelo e versão registrada
PREFIXO_REGISTRO = "atlas-br-"
SUFIXOS_REGISTRO = {"dev": "_dev", "hml": "_hml", "prod": ""}  # os três ambientes podem dividir um MLflow


def nome_registrado(modelo_nome, horizonte, env):
    if env not in SUFIXOS_REGISTRO:
        raise ValueError(f"ambiente inválido {env!r} (use {', '.join(SUFIXOS_REGISTRO)})")
    return f"{PREFIXO_REGISTRO}{modelo_nome}-h{horizonte}{SUFIXOS_REGISTRO[env]}"


def gravar(df, nome):
    caminho = trabalho / nome
    df.to_csv(caminho, index=False) if nome.endswith(".csv") else df.to_parquet(caminho, index=False)
    mlflow.log_artifact(str(caminho))


tags = {
    "atlas.horizon": str(cfg.horizon),
    "atlas.pipeline_run": pipeline_run,
    "atlas.model_family": modelo.family,
    "atlas.forecast_model": modelo.name,
}
with atlas_run(settings, EXPERIMENT, data_version=data_version, run_name=modelo.name, extra_tags=tags) as run:
    mlflow.log_params(
        {
            **cfg.as_params(),
            "val_start": str(datas.val_start.date()),
            "test_start": str(datas.test_start.date()),
            "n_train": len(prep.train),
            "n_val": len(prep.val),
            "n_test": len(prep.test),
        }
    )
    # depois do ajuste: alguns valores só existem aqui (melhor iteração, épocas, busca)
    mlflow.log_params({f"model.{k}": v for k, v in modelo.params().items()})
    mlflow.log_metrics(metricas)
    gravar(pred, "predictions.parquet")
    gravar(by_uf, "metrics_by_uf.csv")
    if oof is not None:
        gravar(oof, "oof_predictions.parquet")
    gravar(futuro, "future_predictions.parquet")
    mlflow.log_artifacts(str(pasta_figuras), "figures")
    if figuras_falharam:
        mlflow.set_tag("atlas.figures_failed", ",".join(figuras_falharam))
    model_uri = modelo.log_model(prep.test if len(prep.test) else prep.val)
    versao_registrada = (
        register_model(settings, model_uri, nome_registrado(modelo.name, cfg.horizon, settings.atlas_env))
        if register
        else None
    )
run_id = run.info.run_id
print(f"run_id={run_id}")
print(f"modelo registrado: {nome_registrado(modelo.name, cfg.horizon, settings.atlas_env) if register else '-'} v{versao_registrada}")
print(f"experimento: atlas/{EXPERIMENT}  data_version={data_version}")
shutil.rmtree(trabalho, ignore_errors=True)
"""

# --------------------------------------------------------------------------------------------
CELULAS["resultado"] = """\
# Resultado do passo: o Airflow lê este arquivo para passar o run_id adiante (vazio = só imprime)
resultado = {
    "run_id": run_id,
    "model_version": versao_registrada,
    "metrics": {k: round(float(v), 6) for k, v in metricas.items() if k.startswith("test_")},
}
if result_path:
    Path(result_path).parent.mkdir(parents=True, exist_ok=True)
    Path(result_path).write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
print(json.dumps(resultado, ensure_ascii=False))
"""

assert set(CELULAS) == set(ORDEM), set(CELULAS) ^ set(ORDEM)
