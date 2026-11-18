---
id: lstm
nome: LSTM
resumo: "Rede neural que lê a sequência das últimas semanas."
entradas: "As 12 últimas semanas de incidência, a UF (como vetor aprendido) e a época do ano."
alvo: "Incidência de casos prováveis por 100 mil habitantes, 1 a 4 semanas à frente da origem."
hiperparametros:
  - "Duas camadas LSTM (60 e 20 unidades)"
  - "Dropout 0,5"
  - "Até 200 épocas, parada antecipada com paciência 12"
  - "Lotes de 64 janelas"
referencia: "Hochreiter e Schmidhuber, Long Short-Term Memory (1997)."
---

O LSTM é uma rede neural feita para sequências. Ele lê as semanas em ordem e guarda na “memória” o que importa: se a curva está subindo, se acelerou, se já passou do pico.

Cada UF tem uma representação própria aprendida, o que permite ao modelo dar um peso diferente à mesma tendência em estados diferentes. Leva mais tempo para treinar que os demais.
