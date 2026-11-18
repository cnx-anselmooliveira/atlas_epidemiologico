---
id: chronos
nome: Chronos
resumo: "Modelo pré-treinado em muitas séries de tempo."
entradas: "As últimas semanas de incidência da UF, sem treino adicional (zero-shot)."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "Chronos-Bolt small (amazon/chronos-bolt-small)"
  - "Sem ajuste fino: usa o modelo como foi publicado"
  - "Intervalo pelos quantis 2,5% e 97,5% da previsão"
referencia: "Ansari et al., Chronos: Learning the Language of Time Series (2024)."
---

O Chronos é um modelo de fundação: foi treinado por terceiros em um enorme conjunto de séries de tempo de áreas variadas e aprendeu padrões gerais de tendência e sazonalidade.

Aqui ele é usado “como está” (zero-shot), sem aprender com a dengue. É um bom ponto de comparação: se os modelos treinados nos nossos dados não ganham dele, o treino específico não está agregando.
