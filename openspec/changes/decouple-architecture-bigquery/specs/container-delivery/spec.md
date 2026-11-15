# Spec Delta

## Purpose

Produzir, a partir do repositório, imagens Docker testadas e versionadas de cada componente e publicá-las no DockerHub sem passos manuais.

## ADDED Requirements

### Requirement: Build por componente alterado
O CI SHALL buildar e publicar a imagem de um componente (backend, frontend, pipelines/airflow) somente quando arquivos daquele componente ou do seu workflow mudarem.

#### Scenario: Mudança só no frontend
- **WHEN** um commit na branch `main` altera apenas arquivos de `frontend/`
- **THEN** somente a imagem do frontend é buildada e publicada

### Requirement: Validação antes da publicação
O CI SHALL executar lint e testes do componente antes do build, e não SHALL publicar a imagem se alguma etapa falhar.

#### Scenario: Teste do backend falhando
- **WHEN** um teste do backend falha em um push para `main`
- **THEN** o workflow termina com falha e nenhuma imagem nova do backend é publicada

### Requirement: Pull requests não publicam
Em pull requests o CI SHALL executar validação e build, sem publicar imagens nem disparar deploy.

#### Scenario: PR alterando o backend
- **WHEN** um pull request altera arquivos de `backend/`
- **THEN** lint, testes e build do backend rodam
- **AND** nenhuma imagem é enviada ao DockerHub

### Requirement: Tags imutáveis
Cada imagem publicada SHALL receber uma tag imutável derivada do commit (SHA curto) e a tag `latest`; tags de versão `vX.Y.Z` SHALL ser publicadas quando houver tag git correspondente.

#### Scenario: Push em main
- **WHEN** o commit `abc1234` em `main` publica a imagem do backend
- **THEN** o DockerHub tem `<usuario>/atlas-epidemiologia-backend:abc1234` e `:latest` apontando para o mesmo digest

### Requirement: Imagem sem segredos
Nenhuma imagem publicada SHALL conter credenciais (chave de service account, tokens) nem arquivos `.env`.

#### Scenario: Inspeção da imagem
- **WHEN** o sistema de arquivos de uma imagem publicada é inspecionado
- **THEN** não há arquivo de chave GCP nem `.env`

### Requirement: Frontend configurável em runtime
A imagem do frontend SHALL obter a URL base da API em tempo de execução do container, de forma que a mesma imagem sirva qualquer ambiente.

#### Scenario: Mesma imagem, outra API
- **WHEN** o container do frontend sobe com a URL da API definida por variável de ambiente
- **THEN** as chamadas do navegador vão para essa URL, sem rebuild da imagem
