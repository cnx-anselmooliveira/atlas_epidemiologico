# Spec Delta

## MODIFIED Requirements

### Requirement: Imagem não precisa reconstruir por DAG ou notebook
A publicação das imagens do Airflow, `ml` e `ml-notebook` SHALL deixar de ser disparada por alterações que mudem só DAGs ou notebooks. Alterações no pacote `atlas_ml`, nos venvs, no Dockerfile ou na configuração SHALL continuar disparando a publicação.

#### Scenario: Alteração só em DAG
- **WHEN** um merge muda apenas arquivos de `airflow/dags`
- **THEN** o workflow de publicação da imagem do Airflow não roda

#### Scenario: Alteração só em notebook
- **WHEN** um merge muda apenas arquivos de `ml/notebooks`
- **THEN** os workflows de publicação das imagens do Airflow, `ml` e `ml-notebook` não rodam

#### Scenario: Alteração no pacote de ML
- **WHEN** um merge muda `ml/src`
- **THEN** a imagem do Airflow é reconstruída e publicada
