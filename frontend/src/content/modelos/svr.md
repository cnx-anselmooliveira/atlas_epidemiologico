---
id: svr
nome: SVR
resumo: "Ajusta uma curva com margem de tolerância ao erro."
entradas: "As 12 últimas semanas de incidência da UF, a UF e a época do ano, padronizadas."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "Núcleo (kernel) escolhido entre rbf, poly e sigmoid"
  - "Parâmetros C, gamma e epsilon buscados em grade"
  - "Epsilon de 0,01 a 0,2: erros menores que isso não pesam"
referencia: "Drucker et al., Support Vector Regression Machines (1996)."
---

O SVR procura a curva que passa “perto o suficiente” dos dados: erros menores que uma margem de tolerância (epsilon) não contam, e só os pontos que ficam fora dessa margem definem a curva.

Isso o torna estável diante de ruído, como as oscilações de notificação entre semanas. Os parâmetros são escolhidos numa busca em grade com validação.
