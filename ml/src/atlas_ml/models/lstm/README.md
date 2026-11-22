# LSTM (PyTorch)

Rede recorrente sobre as janelas de incidência, com embedding de UF. Modelo-base do ensemble.

- **Referência:** notebook de LSTM do ESA-UNICEF Dengue Forecast ([levantamento](../../../../../docs/referencias/esa-unicef-dengue-forecast.md)), que era em Keras.
- **Arquitetura:**
  1. `Embedding(27, 4)` da UF, concatenado a cada passo da janela;
  2. `LSTM(60)`, dropout 0,5 e `LSTM(20)`;
  3. o último estado, concatenado a `sin`/`cos` da semana do alvo, passa por `Linear(1)`.
- **Entrada por passo:** `log1p(incidência)` padronizada, mais os canais de `cfg.features` (padrão: 8 canais do SINAN como taxa por 100 mil em `log1p`, mais altitude e declividade), ou seja, 11 canais por passo.
- **Capacidade registrada:** `model.n_inputs_per_step` e `model.n_trainable_params`, para comparar com a referência.

## O que mudou em relação ao original

- **Otimizador:** Adam com `lr=1e-3` de fato aplicado. No original, o otimizador configurado era ignorado por bug.
- **Early stopping:** só na validação (paciência 12), restaurando os melhores pesos.
- **Aumento de dados:** só no treino.
- **Escalonamento:** ajustado só no treino.
- **Reprodutibilidade:** `torch.manual_seed`, `use_deterministic_algorithms(True)` e embaralhamento por gerador com semente. A variação entre execuções fica abaixo de 2%.
- **Previsões out-of-fold** (`oof_predictions.parquet`) para o ensemble.

## Hiperparâmetros

| Parâmetro | Valor |
|---|---|
| `emb` | 4 |
| `hidden1` / `hidden2` | 60 / 20 |
| `dropout` | 0,5 |
| `lr` | 1e-3 |
| `batch_size` | 64 |
| `max_epochs` | 200 |
| `patience` | 12 |

## Registro

- **Modelo:** `mlflow.pytorch` em formato pickle, porque o `forward` tem três entradas e o formato `pt2` não as descreve na assinatura. Registrado como `atlas-br-lstm`.
- **Contrato de entrada:** `model_extra/input_contract.json` traz as entradas, a média e o desvio do scaler e a fórmula de volta para incidência.

## Tempo esperado em CPU

Dezenas de minutos no painel real: modelo final e 3 ajustes OOF, com early stopping.
