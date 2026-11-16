# Tasks

## 1. Projeto dbt no repositório

- [ ] 1.1 Varrer `utfpr_dengue/` atrás de segredos (chaves, `private_key`, senhas, caminhos de keyfile) e confirmar que `target/`, `logs/` e `dbt_packages/` estão ignorados; verificar com `git status` e o grep de padrões sem achados
- [ ] 1.2 Criar `utfpr_dengue/pyproject.toml` (dbt-core + dbt-bigquery, Python 3.12) com `uv.lock`, `utfpr_dengue/profiles.yml` por variáveis de ambiente e os scripts `dbt.ps1`/`dbt.sh` (padrão `DBT_BQ_KEYFILE=platform/secrets/training-sa.json`); verificar `dbt debug` conectando sem `~/.dbt/profiles.yml`
- [ ] 1.3 Conferir se a service account local tem escrita nos datasets `silver` e `gold` (`dbt run --select silver_dim_country` ou permissão via `bq show`); registrar o resultado no `utfpr_dengue/README.md`
- [ ] 1.4 Commits por assunto em `dev` (`build(dbt): projeto utfpr_dengue no repositório`; `build(dbt): execução reprodutível com uv e profile por ambiente`); verificar com `git log --oneline -2` e que nenhuma chave entrou

## 2. Macros e população anual

- [ ] 2.1 Criar as macros `sinan_classificacao`, `epi_week_start` e `epi_year`/`epi_week` com comentários de fonte; verificar com `dbt compile` e uma consulta de amostra (`dbt show`) mostrando `"5 "` → `descartado` e a semana de 2024-01-01 no ano epidemiológico correto
- [ ] 2.2 Criar `scripts/gerar_seed_populacao_uf_anual.py` (SIDRA: censos 2000/2010/2022 + estimativas da tabela 6579; interpolado/extrapolado) e gerar `seeds/seed_populacao_uf_anual.csv` com `.yml` de tipos; verificar 27 UFs × todos os anos de 2000 até o ano corrente, sem lacunas, e as origens corretas
- [ ] 2.3 Commits por assunto (`feat(dbt): macros de classificação SINAN e semana epidemiológica`; `feat(dbt): população anual por UF`); verificar `git log --oneline -2`

## 3. Models e testes

- [ ] 3.1 Criar `silver_dengue_casos_uf_semana_brasil` (table, cluster `uf`): data com fallback, UF de residência com fallback, contagens por categoria e fallbacks; verificar com `dbt build --select silver_dengue_casos_uf_semana_brasil` e conferência da soma de `notified_cases` contra a silver de casos
- [ ] 3.2 Criar `silver_relevo_uf_brasil` (cruzamento espacial DEM ADM2 × centroides do IBGE, médias ponderadas por área, taxa de casamento); verificar 27 UFs e registrar a taxa de casamento
- [ ] 3.3 Criar `gold_dengue_casos_provaveis_uf_semanal` (+ `.yml` com descrições das colunas e testes genéricos) e os testes singulares (totais vs silver, prováveis ≤ notificados, semanas completas, relevo 27 UFs, `outro` como aviso); verificar `dbt build --select +gold_dengue_casos_provaveis_uf_semanal` com todos os testes verdes
- [ ] 3.4 Comparar a nova tabela com a `gold_dengue_epi_curve_weekly` (totais por ano, picos por UF, fração de descartados, efeito dos fallbacks) e registrar em `docs/referencias/gold-casos-provaveis-uf.md`; verificar a diferença próxima de 22% explicada pelos descartados
- [ ] 3.5 Commits por assunto (`feat(dbt): agregado de casos por UF e semana e relevo por UF`; `feat(dbt): gold de casos prováveis por UF para modelagem`; `docs: comparação da nova gold com a curva atual`); verificar `git log --oneline -3`

## 4. CI e integração

- [ ] 4.1 Adicionar o job `dbt` ao `.github/workflows/ci.yml` (uv sync + `dbt parse` com variáveis fictícias) e incluí-lo no `ci-ok`; verificar com `actionlint` e o job verde num PR para `hml`
- [ ] 4.2 Atualizar a `add-dengue-forecast-models` (spec `forecast-dataset`, design seção 2 e tarefas 2.2/2.3) para ler `gold_dengue_casos_provaveis_uf_semanal` (`probable_cases`, covariáveis de relevo); verificar `openspec validate add-dengue-forecast-models --strict`
- [ ] 4.3 Atualizar `utfpr_dengue/README.md` (como rodar, profile, nova tabela, testes) e o `README.md` raiz (pasta `utfpr_dengue/` na estrutura); verificar links com lychee
- [ ] 4.4 Commits por assunto (`ci: dbt parse no pipeline`; `docs(openspec): modelos leem a gold de casos prováveis`; `docs: documentação do projeto dbt`); verificar `git log --oneline -3`

## Workflow follow-up

- Abrir uma mudança própria para corrigir a contagem de descartados nas tabelas gold usadas pelo site e pela API, reaproveitando as macros desta mudança.
