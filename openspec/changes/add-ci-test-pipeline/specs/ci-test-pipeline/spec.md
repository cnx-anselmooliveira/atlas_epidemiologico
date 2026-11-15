# Spec Delta

## Purpose

Garantir que nenhum código chegue às branches de homologação (`hml`) e produção (`main`) sem passar por todos os testes automatizados do projeto.

## ADDED Requirements

### Requirement: Gatilhos do pipeline
O pipeline de testes SHALL rodar em todo push nas branches `hml` e `main`, em todo pull request cujo destino seja `hml` ou `main`, e por disparo manual. Ele SHALL NOT rodar em pushes na branch `dev`.

#### Scenario: Pull request para hml
- **WHEN** um pull request de `dev` para `hml` é aberto ou atualizado
- **THEN** o pipeline de testes roda sobre o commit do pull request

#### Scenario: Push em dev
- **WHEN** um commit é enviado para `dev`
- **THEN** o pipeline de testes não é disparado

### Requirement: Cobertura de todos os testes do projeto
O pipeline SHALL executar:
- lint e formato do Python;
- lint dos scripts shell, dos workflows e dos composes;
- os testes do pacote `ml`, incluindo os marcados como `models`;
- o build de todas as imagens do projeto;
- o teste de integridade das DAGs na imagem do Airflow;
- o teste de ponta a ponta da plataforma;
- o build do frontend;
- a validação estrita das mudanças OpenSpec.

#### Scenario: Teste do pacote ml falhando
- **WHEN** um teste do pacote `ml` falha
- **THEN** o pipeline termina com falha e indica o job e o teste que falharam

#### Scenario: Dockerfile quebrado
- **WHEN** o build de qualquer imagem do projeto falha
- **THEN** o pipeline termina com falha

### Requirement: Sem segredos e sem serviços externos
O pipeline SHALL rodar sem credenciais do GCP e sem acesso ao BigQuery ou ao bucket. Testes que dependem desses serviços SHALL usar simulações ou ficar fora do pipeline. Imagens construídas no pipeline SHALL NOT ser publicadas por ele.

#### Scenario: Pull request de fork
- **WHEN** um pull request vem de um fork, sem acesso aos secrets do repositório
- **THEN** o pipeline roda completo e chega ao mesmo resultado que num pull request interno

### Requirement: Teste de ponta a ponta da plataforma
O pipeline SHALL subir a plataforma de dev (Postgres, MLflow e Airflow) a partir do código do commit, disparar a DAG de exemplo e verificar que:
- a execução termina com sucesso;
- a run no MLflow tem as tags `atlas.*`;
- o modelo foi registrado.

#### Scenario: DAG de exemplo quebrada
- **WHEN** uma mudança faz a DAG `atlas_ml_example_training` falhar
- **THEN** o job de ponta a ponta falha
- **AND** os logs dos serviços ficam anexados à execução do pipeline

### Requirement: Check único obrigatório nas branches protegidas
O pipeline SHALL expor um check agregado que só passa quando todos os jobs passam. As branches `hml` e `main` SHALL exigir esse check e um pull request para receber mudanças.

#### Scenario: Merge com teste falhando
- **WHEN** um pull request para `main` tem o check agregado com falha
- **THEN** o GitHub bloqueia o merge

#### Scenario: Push direto em main
- **WHEN** alguém tenta enviar um commit direto para `main`, sem pull request
- **THEN** o push é rejeitado

### Requirement: Reuso pela publicação de imagens
O pipeline SHALL poder ser chamado por outros workflows, de modo que a publicação de imagens para `hml` e `X.Y` só aconteça depois de ele passar no mesmo commit.

#### Scenario: Publicação de hml
- **WHEN** um push em `hml` dispara a publicação de imagens
- **THEN** as imagens só são enviadas ao DockerHub depois de o pipeline de testes passar naquele commit
