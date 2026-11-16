# Proposal

## Why

Os modelos de previsão (`add-dengue-forecast-models`) foram planejados sobre a `gold_dengue_epi_curve_weekly`. A inspeção do BigQuery e do projeto dbt (`utfpr_dengue/`) mostrou que essa tabela não serve como alvo de modelagem:

- **Conta todas as notificações, inclusive as descartadas.** A silver semanal faz `count(*)` sem filtrar a classificação, então cerca de **7,2 milhões de descartados (21,6%)** entram na série. O indicador oficial é o de **casos prováveis**: notificações menos descartados.
- **Usa a semana e a UF de notificação.** O certo para modelar transmissão é a semana do **início dos sintomas** e a UF de **residência**: 131 mil casos têm UF de residência diferente da de notificação.
- **Mistura dados da OPAS sem UF** nas semanas finais do Brasil.
- **Os códigos de classificação do SINAN vêm com espaço no fim a partir de 2013** ("5 " ≠ "5"). Sem padronização, qualquer filtro falha em silêncio.
- **Tem população de um único ano** (Censo 2022) para 2000–2026.

Em vez de alterar as tabelas que o site e a API usam, a proposta cria uma **tabela gold nova, própria para modelagem**.

## What Changes

- **Projeto dbt `utfpr_dengue/` versionado no repositório**, como trazido do projeto antigo, com `profiles.yml` lendo projeto, localização e credencial de variáveis de ambiente (sem chave em arquivo pessoal) e execução reprodutível via uv.
- **Padronização da classificação final do SINAN** (trim + mapeamento documentado: 1–4 e 10–12 confirmados por tipo, 5 descartado, 8 inconclusivo, nulo/0 em investigação), num model intermediário reutilizável.
- **Nova tabela gold `gold_dengue_casos_provaveis_uf_semanal`**, com grão UF de residência × semana epidemiológica do início dos sintomas, de 2000 até a última semana disponível. Colunas:
  - casos prováveis (alvo);
  - casos notificados, descartados, confirmados, graves e com sinais de alarme;
  - óbitos;
  - população do ano;
  - incidência por 100 mil;
  - relevo da UF (elevação e declividade médias), agregado dos municípios do Copernicus DEM por cruzamento espacial;
  - semanas sem notificação, explícitas com zero.
- **População anual por UF** (estimativas do IBGE + censos, com interpolação marcada nos anos sem estimativa), como seed gerado por script versionado.
- **Testes de dados** no dbt:
  - unicidade de UF × semana;
  - 27 UFs;
  - casos prováveis ≤ notificados;
  - incidência não negativa;
  - total de prováveis igual ao da silver filtrada.
- **Ajuste da `add-dengue-forecast-models`** para ler o painel dessa tabela: spec `forecast-dataset`, design e tarefas.

## Capabilities

### New Capabilities
- `forecast-gold-dataset`: a tabela gold de casos prováveis por UF e semana para modelagem, com definição do alvo, grão, tratamento de datas e lugar, população anual, covariáveis estáticas e testes de qualidade.
- `dbt-project-runtime`: como o projeto dbt é executado de forma reprodutível (dependências fixadas, profile por variáveis de ambiente, sem credenciais versionadas) e validado sem acesso ao BigQuery.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/. A spec forecast-dataset da add-dengue-forecast-models (ainda não arquivada) é ajustada diretamente nos artefatos daquela mudança. -->

## Impact

- **Código:**
  - `utfpr_dengue/` (novo no repositório);
  - models `utfpr_dengue/models/silver/silver_dengue_casos_classificados_brasil.sql`, `silver_relevo_uf_brasil.sql` e `gold/gold_dengue_casos_provaveis_uf_semanal.sql` (+ `.yml`);
  - macro de semana epidemiológica;
  - seed e script de população anual.
- **BigQuery:**
  - nova tabela em `gold`;
  - um model silver materializado como tabela (casos classificados por UF e semana) para evitar reprocessar 33 milhões de linhas a cada build;
  - nenhuma tabela existente muda.
- **`add-dengue-forecast-models`:** a consulta do módulo 2, ainda não commitado, passa a ler a nova tabela. Interface do painel, janelas e modelos não mudam.
- **CI:** o `ci.yml` ganha um job `dbt` com `dbt parse` (sem credenciais).
- **Fora de escopo:**
  - corrigir as tabelas gold atuais usadas pelo site e pela API (registrado como recomendação);
  - versão por município;
  - outros países;
  - covariáveis climáticas e de satélite.
