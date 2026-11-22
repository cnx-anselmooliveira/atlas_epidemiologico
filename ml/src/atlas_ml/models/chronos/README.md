# Chronos-Bolt (zero-shot)

Modelo fundacional de séries temporais da Amazon, usado sem treino como comparador fora do stacking.

- **Referência:** o Chronos citado no levantamento do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)).
- **Checkpoint:** `amazon/chronos-bolt-small`, via `chronos-forecasting`, em CPU.
- **Entrada univariada:** usa só a incidência da UF; os canais do SINAN não entram (o Chronos-Bolt não recebe covariáveis). A run registra `model.inputs`.
- **Contexto:** para cada janela (UF, origem t), todo o histórico de incidência da UF até t, limitado a `context_weeks=512`. Por isso o modelo recebe o painel (`use_panel`), não só a janela.
- **Previsão:**
  - mediana (quantil 0,5) no passo t + `horizon`;
  - quantis 0,1 e 0,9 como `lower`/`upper` (intervalo de **80%**, registrado no parâmetro `interval`).

## Reprodutibilidade

- A revisão do checkpoint (commit do Hugging Face) é resolvida na hora do ajuste e registrada no parâmetro `model.revision` e na tag `atlas.checkpoint`.
- O pyfunc registrado recarrega exatamente essa revisão.

## Cache

Com `HF_HOME`, o checkpoint é baixado uma vez para o volume `hf-cache`, montado em `/opt/airflow/hf-cache` no Airflow e em `/home/atlas/hf-cache` no Jupyter. Em rede com inspeção TLS, o download usa a CA de `EXTRA_CA_PATH`.

## Registro

`pyfunc` com entrada longa (`series_id`, `value`, em ordem temporal) e saída da mediana em t + `horizon`. Registrado como `atlas-br-chronos`.

## Testes

Usam um pipeline falso, sem download, que devolve a persistência ±20%. Assim conferem o contexto, os quantis e o registro sem acesso à rede.

## Tempo esperado em CPU

27 UFs × 104 origens (validação e teste), em lotes de 64 contextos: alguns minutos.
