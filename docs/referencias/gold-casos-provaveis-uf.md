# Gold de casos prováveis por UF: comparação com a curva atual

Comparação entre a nova `gold.gold_dengue_casos_provaveis_uf_semanal` e a `gold.gold_dengue_epi_curve_weekly` (Brasil, linhas com UF). Os números vêm do build de 16/11/2026, com o SINAN notificado até 29/06/2026.

## Perfil da nova tabela

| Item | Valor |
|---|---|
| Linhas | 37.341 (27 UFs × 1.383 semanas) |
| Período | semana de 02/01/2000 a semana de 28/06/2026 |
| Notificações | 33.462.008 |
| Casos prováveis (`probable_cases`) | 26.251.384 |
| Descartados / notificações | 21,55% |
| Fallback de data (início dos sintomas incoerente ou ausente) | 0,89% |
| Fallback de lugar (sem UF de residência) | 0,016% |
| População interpolada | 2.808 linhas (anos de 2007 e 2023) |
| Relevo: polígonos casados por contenção | ≥ 98% no país; AP 87,5%, RO 92,3%, RR 93,3% |

## Totais por ano

`dif` = 1 − prováveis / total da curva atual.

| Ano | Notificações | Prováveis | Curva atual | dif |
|---|---:|---:|---:|---:|
| 2000 | 173.644 | 137.363 | 172.854 | 20,5% |
| 2005 | 261.972 | 151.369 | 261.268 | 42,1% |
| 2010 | 1.375.433 | 1.020.604 | 1.381.254 | 26,1% |
| 2015 | 2.424.364 | 1.718.295 | 2.398.060 | 28,3% |
| 2019 | 2.263.833 | 1.555.438 | 2.261.956 | 31,2% |
| 2020 | 1.486.778 | 951.260 | 1.495.117 | 36,4% |
| 2021 | 1.010.344 | 531.980 | 1.010.359 | 47,3% |
| **2022** | 1.393.892 | 1.393.888 | 1.393.877 | **0,0%** |
| 2023 | 1.508.653 | 1.508.653 | 1.508.653 | 0,0% |
| 2024 | 6.466.979 | 6.466.979 | 6.466.979 | 0,0% |
| 2025 | 1.727.216 | 1.727.216 | 1.728.234 | 0,1% |
| 2026 (parcial) | 399.804 | 399.804 | 398.451 | −0,3% |

As notificações batem com a curva atual ano a ano. A diferença entre as duas é a semana usada (início dos sintomas × notificação) e a UF (residência × notificação).

## Achado: a fonte não traz descartados a partir de 2022

Classificação final (CLASSI_FIN) por ano de notificação na `silver_dengue_cases_brasil`:

| Código | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|
| 5 (descartado) | 535.808 | 478.419 | **621** | **0** | **0** | **0** |
| 8 (inconclusivo) | 161.292 | 83.193 | 149.177 | 207.754 | 615.364 | 158.548 |
| 10 (dengue) | 779.203 | 442.438 | 1.223.671 | 1.276.131 | 5.701.346 | 1.461.766 |

A partir de 2022, os microdados carregados só trazem notificações não descartadas. Consequências:

- **Curva atual (`gold_dengue_epi_curve_weekly`):** soma todas as notificações. Até 2021 inclui de 20% a 53% de descartados por ano; depois, nenhum. A série tem uma quebra de nível artificial em 2022 que um modelo aprenderia como sinal.
- **Nova gold (`probable_cases`):** mesma definição em toda a série (notificações não descartadas), sem a quebra. É a definição de caso provável dos boletins do Ministério da Saúde.
- **Diferença média esperada de cerca de 22%:** confirmada no total (21,55%). Por ano, ela vai de 19% a 53% até 2021 e é zero depois.

## Recomendações

- **Modelos:** usar `probable_cases` como alvo. `notified_cases` não é comparável entre antes e depois de 2022.
- **Site e API:** corrigir a curva atual numa mudança própria, reaproveitando as macros `sinan_classificacao` e `epi_week_*` (registrado como follow-up da `add-gold-casos-provaveis-uf`).
- **Ingestão:** conferir na origem dos microdados (basedosdados / SINAN) se os descartados de 2022 em diante existem e foram filtrados na carga. Se existirem, recarregá-los melhora `discarded_cases`; os casos prováveis não mudam.
