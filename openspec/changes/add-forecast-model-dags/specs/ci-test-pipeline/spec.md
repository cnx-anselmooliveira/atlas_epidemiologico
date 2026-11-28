# Spec Delta

## MODIFIED Requirements

### Requirement: Cobertura de todos os testes do projeto
Fora da via rápida, o pipeline SHALL executar:
- lint e formato do Python;
- lint dos scripts shell, dos workflows e dos composes;
- os testes do pacote `ml`, incluindo os marcados como `models`;
- o build de todas as imagens do projeto;
- o teste de integridade das DAGs na imagem do Airflow;
- o teste de ponta a ponta da plataforma;
- o build do frontend;
- a validação estrita das mudanças OpenSpec.

#### Scenario: Teste do pacote ml falhando
- **WHEN** um teste do pacote `ml` falha num pipeline completo
- **THEN** o pipeline termina com falha e indica o job e o teste que falharam

#### Scenario: Dockerfile quebrado
- **WHEN** um commit muda um Dockerfile e o build de alguma imagem do projeto falha
- **THEN** o pipeline termina com falha

### Requirement: Check único obrigatório nas branches protegidas
O pipeline SHALL expor um check agregado que só passa quando todos os jobs que deviam rodar passam. Um job pulado SHALL reprovar o check, exceto os jobs que a via rápida dispensa, quando a via rápida foi escolhida. As branches `hml` e `main` SHALL exigir esse check e um pull request para receber mudanças.

#### Scenario: Merge com teste falhando
- **WHEN** um pull request para `main` tem o check agregado com falha
- **THEN** o GitHub bloqueia o merge

#### Scenario: Push direto em main
- **WHEN** alguém tenta enviar um commit direto para `main`, sem pull request
- **THEN** o push é rejeitado

#### Scenario: Job pulado fora da via rápida
- **WHEN** o pipeline completo roda e o job das imagens é pulado porque um job anterior falhou
- **THEN** o check agregado falha

## ADDED Requirements

### Requirement: Escolha da via rápida
O pipeline SHALL escolher a via rápida quando todos os arquivos alterados estão em `airflow/dags/` (exceto `pyproject.toml` e `uv.lock` do projeto dbt), em `airflow/tests/`, em `ml/notebooks/`, em `openspec/`, em `docs/` ou são arquivos Markdown. Uma chamada vinda da publicação de imagens ou um disparo manual SHALL usar sempre o pipeline completo.

#### Scenario: PR com DAG e pacote ml
- **WHEN** um pull request muda uma DAG e um arquivo de `ml/src`
- **THEN** o pipeline completo roda

#### Scenario: Dependência do dbt
- **WHEN** um pull request muda `airflow/dags/utfpr_dengue/uv.lock`
- **THEN** o pipeline completo roda

#### Scenario: Chamada pela publicação de imagens
- **WHEN** a publicação de uma imagem chama o pipeline
- **THEN** o pipeline completo roda, qualquer que seja a mudança

### Requirement: Jobs da via rápida
Na via rápida o pipeline SHALL rodar lint, verificação dos notebooks, integridade das DAGs, segredos, OpenSpec, stack e promoção, e SHALL NOT rodar o build das imagens, o e2e da plataforma, o frontend, o backend nem os testes do pacote `ml`.

#### Scenario: PR só com DAG
- **WHEN** um pull request de `dev` para `hml` muda só `airflow/dags/atlas_forecast_lstm.py` e `airflow/tests/test_dags.py`
- **THEN** o pipeline roda na via rápida, a integridade das DAGs é testada e o check agregado passa sem os jobs dispensados

#### Scenario: DAG quebrada na via rápida
- **WHEN** um pull request só de DAG introduz uma DAG que não importa
- **THEN** o job de integridade das DAGs falha e o check agregado falha
