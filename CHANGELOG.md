# Changelog

Todas as mudanças relevantes do projeto são registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa versões `vX.Y` (tags em `main`). Cada versão publica as imagens Docker `X.Y` e uma [GitHub Release](https://github.com/cnx-anselmooliveira/atlas_epidemiologico/releases) com notas detalhadas.

## [Não lançado]

### Adicionado
- **Plataforma de ML local** (`platform/`): Postgres, MLflow 3.18 e Airflow 3.3 em compose, com artefatos no GCS (`gs://ppgcc-bucket/mlflow/dev/`) ou em volume local, e Jupyter opcional.
- **Pacote `atlas_ml`** com o CLI `atlas-ml`:
  - configuração por ambiente;
  - tags de reprodutibilidade `atlas.*` em toda run;
  - leitura de features do BigQuery com versão dos dados;
  - experimento de exemplo;
  - promoção de modelos `@dev` → `@hml` → `@prod`.
- **Imagens:**
  - servidor MLflow com autenticação;
  - Airflow com o `atlas_ml` num ambiente isolado e a DAG `atlas_ml_example_training`;
  - imagem de treino.
- **Núcleo de previsão de incidência por UF** (em andamento): painel da gold do SINAN, divisões temporais sem vazamento.
- **Documentação:** levantamento dos modelos do ESA-UNICEF Dengue Forecast Project.
- **Governança:**
  - README com badges;
  - licença MIT;
  - CONTRIBUTING;
  - código de conduta;
  - política de segurança com reporte privado;
  - modelos de issue e PR;
  - CITATION.cff;
  - publicação de releases a partir das tags.

### Planejado
- Pipeline de testes no GitHub Actions para `hml` e `main` (`add-ci-test-pipeline`).
- Seis modelos de previsão: baseline bayesiano, CatBoost, LSTM, SVR, Chronos e ensemble (`add-dengue-forecast-models`).
- Publicação de imagens `dev`/`hml`/`X.Y` e stacks de homologação e produção (`add-ml-platform`).

<!-- Ao publicar uma versão: renomeie [Não lançado] para [X.Y] - AAAA-MM-DD, crie um novo [Não lançado]
     vazio acima e adicione o link da versão abaixo. -->
[Não lançado]: https://github.com/cnx-anselmooliveira/atlas_epidemiologico/commits/dev
