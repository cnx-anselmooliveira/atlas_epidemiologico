---
id: catboost
nome: CatBoost
resumo: "Árvores de decisão que corrigem os erros umas das outras."
entradas: "As 12 últimas semanas de incidência da UF, a UF e a época do ano (semana epidemiológica)."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "5000 iterações com parada antecipada"
  - "Taxa de aprendizado 0,03"
  - "Profundidade das árvores 6"
referencia: "Prokhorenkova et al., CatBoost: unbiased boosting with categorical features (2018)."
---

O CatBoost constrói uma árvore de decisão pequena, vê onde ela erra e constrói a próxima para corrigir esses erros, repetindo milhares de vezes. A previsão final é a soma de todas as árvores.

Ele lida bem com a UF como categoria e com a sazonalidade da dengue (mais casos no verão e no outono), e é rápido de treinar. Não devolve intervalo de incerteza.
