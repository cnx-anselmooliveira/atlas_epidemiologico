# Arquitetura de dados — dengue América do Sul (Bronze → Silver → Gold)

## Mapa da arquitetura

```
FONTES (raw, já carregadas)                    BRONZE                                  SILVER                                    GOLD
─────────────────────────────                  ──────                                  ──────                                    ────
raw_uftpr_microdados_brasil          ──►  bronze_dengue_brasil            ──┐
  (SINAN, case-level, 151 cols)                                             │
municipios (br_ms_sinan.duckdb)      ──►  bronze_dim_municipio_brasil     ──┼──► silver_dim_municipio_brasil
                                                                             │
raw_uftpr_microdados_colombia         ──►  bronze_dengue_colombia          ──┤
  (SIVIGILA, case-level)                                                    │
raw_uftpr_microdados_peru             ──►  bronze_dengue_peru              ──┤
  (CDC-MINSA, case-level)                                                   │     silver_dengue_cases_brasil        ──┐
raw_uftpr_microdados_argentina        ──►  bronze_dengue_argentina         ──┤       (fato, grão = 1 caso)             │
  (SNVS, agregado depto×semana×fx.et.)                                      │                                          │
raw_uftpr_microdados_equador          ──►  bronze_dengue_equador_weekly_agg├──┤                                          ├──► gold_dengue_kpi_country_year
                                       ──►  bronze_dengue_equador_cases    ──┤     silver_dengue_weekly_cases        ──┤      gold_dengue_kpi_country_month
  (SIVE-ALERTA/OBSALUD, 2 planilhas)                                        │       (fato, grão = país×UF/depto×      │      gold_dengue_growth_wow_country
                                                                             │        ano×semana epi, UNION ALL        │      gold_dengue_top_admin1_ranking
raw_uftpr_microdados_bolivia           ──►  bronze_dengue_bolivia          ──┤        das 8 fontes acima)               │      gold_dengue_brasil_demographics
  (PAHO/PLISA, agregado depto×semana)                                      │                                          │      gold_dengue_data_quality
                                                                             │                                          │
raw_uftpr_paho_dengue                  ──►  bronze_dengue_paho_americas    ──┘                                          │
  (PAHO/ARBO, fallback, país×semana,          silver_dim_country ─────────────────────────────────────────────────────┘
   cumulativo dentro do ano)                    (dimensão estática: país, status da fonte, frequência, link)
```

Tabelas Gold adicionais no estilo dos gráficos do info.dengue.mat.br (todas a partir de
`silver_dengue_weekly_cases`, mais `bronze_dengue_paho_americas` para população):

- `gold_dengue_epi_curve_weekly` — curva de casos por semana, com média móvel de 3 semanas e comparação com a mesma semana do ano anterior.
- `gold_dengue_alert_level_weekly` — nível de alerta verde/amarelo/laranja/vermelho (proxy simplificado por percentis históricos, não é o MEM oficial).
- `gold_dengue_incidence_rate_country_weekly` — incidência por 100 mil habitantes, só em nível de país (sem fonte de população subnacional carregada).

## Decisões de modelagem

1. **Bronze é 1:1 com a fonte raw**, uma tabela bronze por tabela raw (Equador vira duas, pois a fonte raw já une duas planilhas com grãos incompatíveis — DSSA é agregado semanal por faixa etária/sexo, DCSA_DG é linelist de dengue grave).
2. **Grão comum na Silver**: como Brasil/Colômbia/Peru/Equador-casos são *linelist* (1 linha = 1 caso) e Bolívia/Argentina/Equador-agregado/PAHO já vêm agregados, o único grão que permite `UNION ALL` sem perda de informação é **país × unidade administrativa (UF/depto/provincia) × ano epidemiológico × semana epidemiológica**. `silver_dengue_weekly_cases` agrega os linelists para esse grão e faz passthrough dos já agregados.
3. **Brasil mantém um fato adicional em nível de caso** (`silver_dengue_cases_brasil`), pois é a única fonte com detalhe clínico/demográfico rico (sintomas, sorotipo, comorbidades) — perder esse grão no `UNION ALL` genérico seria jogar fora informação relevante.
4. **PAHO é usado como fallback**: por ser o único source com Paraguai, Chile, Uruguai, Venezuela etc. na `silver_dim_country`, mas o "Total of Dengue Cases" é cumulativo dentro do ano civil (validado no README) — a Silver descumula isso via `LAG()` por país/ano.
5. **Sem PK nativa exposta** (Brasil/Colômbia/Peru vindos de bases anonimizadas de vigilância): geramos uma chave substituta (`md5` das colunas naturais) só para deduplicação/idempotência, nunca como identificador de paciente real.
6. **Semana epidemiológica → data**: convertida de forma aproximada (`epi_year` + `(epi_week-1)*7` dias) só para permitir agregação mensal na Gold — está documentado como aproximação nas descrições de coluna, não como data exata de calendário epidemiológico de cada país (que varia).
