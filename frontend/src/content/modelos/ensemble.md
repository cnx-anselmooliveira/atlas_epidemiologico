---
id: ensemble
nome: Ensemble
resumo: "Combina as previsões de CatBoost, SVR e LSTM."
entradas: "As 12 últimas semanas de incidência de cada UF, as previsões dos três modelos-base e três extrapolações simples da janela (retas e curva)."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "RandomForest com 300 árvores e profundidade máxima 8"
  - "Modelos-base: CatBoost, SVR e LSTM"
  - "Intervalo de 95% pelos percentis 2,5 e 97,5 entre as árvores"
referencia: "Stacking com previsões out-of-fold (Wolpert, 1992)."
---

O Ensemble é um “comitê”: em vez de confiar em um só modelo, ele pede a previsão de CatBoost, SVR e LSTM e aprende, com uma floresta aleatória, quanto confiar em cada um em cada situação.

Para não “colar” nas respostas, o comitê só aprende com previsões que os modelos-base fizeram sobre semanas que eles não viram no treino (out-of-fold). Junto vão três extrapolações simples da janela, que ajudam quando a curva está em subida ou descida clara.

Como a floresta tem muitas árvores, a divergência entre elas dá o intervalo de 95% mostrado no gráfico.
