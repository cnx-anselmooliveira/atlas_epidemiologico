# Baseline bayesiano (PyMC)

Modelo estatístico interpretável, usado como comparador fora do stacking.

- **Referência:** o baseline bayesiano do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)), no estilo INLA. Aqui o ajuste é com MCMC no PyMC.
- **Modelo:**

```
casos ~ BinomialNegativa(μ, α)
> Entrada univariada: só a incidência da UF (termo defasado); os canais do SINAN não entram. A run registra `model.inputs`.

log μ = log(pop/1e5) + a + u_uf + v_ano + Σ_k (b_k sin(2πk·s/52) + c_k cos(2πk·s/52)) + β · log1p(incidência_{t−H})
```

- **Termos:**
  - `u_uf` e `v_ano`: normais hierárquicos;
  - 2 harmônicos de Fourier para a sazonalidade;
  - um termo defasado (a incidência na origem da janela);
  - offset de população.
- **Anos novos:** anos fora do treino, como o do teste, recebem `v_ano` da priori `N(0, σ_ano)`.

## Previsão e intervalo

A previsão vem da **preditiva posterior** da binomial negativa (gamma-poisson):
- a mediana é `y_pred`;
- os percentis 2,5 e 97,5 formam o intervalo de **95%**.

A cobertura no teste fica em `test_interval_coverage`.

## Diagnósticos

- `rhat_max` e `ess_bulk_min` são registrados como métricas, junto com o tempo de amostragem.
- A tag `atlas.converged` é `true` quando R̂ ≤ 1,05 e ESS ≥ 100.
- O posterior completo vai em `idata.nc`.

## Amostrador

NUTS pelo **nutpie**, compilado com numba, que dispensa o compilador C do PyTensor (o g++ não existe no Windows nem na imagem do Airflow). Valores padrão: 2 cadeias, 500 de tune, 500 draws e `target_accept=0.9`, todos configuráveis.

## Registro

`pyfunc` com a média posterior dos coeficientes (`coef.json`), para servir sem PyMC. Entrada: `uf_code`, `year`, `epi_week`, `lag_incidence`. Registrado como `atlas-br-baseline_bayes`.

## Tempo esperado em CPU

No painel sintético (3 UFs), cerca de 30 s. No painel real, com 27 UFs e cerca de 34 mil janelas de treino, alguns minutos; o tempo medido fica na métrica `sampling_seconds`.
