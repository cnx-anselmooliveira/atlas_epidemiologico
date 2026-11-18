---
id: baseline_bayes
nome: Bayesiano
resumo: "Modelo estatístico que devolve a incerteza da previsão."
entradas: "A incidência da semana H semanas antes, a UF, o ano e a época do ano (ondas seno e cosseno), com a população da UF."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "Contagem de casos binomial negativa"
  - "Efeitos hierárquicos por UF e por ano"
  - "2 cadeias, 500 amostras de aquecimento e 500 de amostragem (nutpie)"
referencia: "Gelman et al., Bayesian Data Analysis; implementado em PyMC."
---

O modelo bayesiano descreve como os casos de dengue surgem: um nível base, mais um efeito de cada UF, de cada ano e da época do ano, mais o quanto a semana de origem pesa no futuro. Em vez de um único número, ele devolve milhares de cenários plausíveis.

Os cenários dão o intervalo de 95% mostrado no gráfico, e por isso ele é o que mais bem comunica a incerteza. Anos novos recebem o efeito médio dos anos vistos.
