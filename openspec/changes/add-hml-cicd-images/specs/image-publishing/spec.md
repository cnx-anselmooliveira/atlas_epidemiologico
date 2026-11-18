# Spec Delta

## Purpose

Publicar no DockerHub, de forma previsível e com falha antecipada, todas as imagens que o Portainer precisa para subir o Atlas.

## ADDED Requirements

### Requirement: Imagens implantáveis publicadas
O repositório SHALL publicar no DockerHub, em `anselmomendes/atlas-epidemiologia-<imagem>`, as imagens `frontend`, `backend`, `airflow`, `mlflow` e `ml` (alvo `runtime`). `ml-notebook`, `postgres` e `redis` SHALL ficar fora da publicação.

#### Scenario: Push em hml
- **WHEN** um commit chega à branch `hml` e altera arquivos de uma imagem
- **THEN** só os workflows dessas imagens rodam e cada uma recebe a tag `hml`

#### Scenario: Primeira publicação sem mudança de arquivo
- **WHEN** o usuário dispara manualmente o workflow de uma imagem na branch `hml`
- **THEN** a imagem é construída e publicada com a tag `hml`, sem precisar alterar nenhum arquivo

#### Scenario: Dependência entre imagens
- **WHEN** um commit altera só `ml/src/`
- **THEN** as imagens `ml` e `airflow` são republicadas, porque o `airflow` embute o `atlas_ml` e as DAGs

### Requirement: Tags pela origem e versão imutável
A tag SHALL vir da origem: branch `dev` → `dev`, `hml` → `hml`, tag `vX.Y` (ou `vX.Y.Z`) → `X.Y`. Uma tag de versão SHALL sair só de commit que está em `main` e SHALL falhar se a versão já existir no DockerHub. Nenhuma tag `latest` SHALL ser publicada.

#### Scenario: Versão repetida
- **WHEN** a tag `v1.2` é criada e `...-backend:1.2` já existe
- **THEN** o job falha sem sobrescrever a imagem

### Requirement: Secrets verificados antes dos testes
Antes de testar e construir, o workflow SHALL conferir que `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN` existem e não estão vazios, sem imprimir seus valores, e SHALL falhar na hora com uma mensagem que diz quais faltam e onde criá-los.

#### Scenario: Secret ausente
- **WHEN** `DOCKERHUB_TOKEN` não está definido
- **THEN** o primeiro job falha em segundos, com a lista do que falta, e nenhum teste nem build é executado

### Requirement: Nada de credencial na imagem
Nenhuma imagem SHALL conter chave de service account, senha, token ou o `.env`. Credenciais SHALL entrar só em execução, por variável de stack ou Docker secret.

#### Scenario: Contexto de build
- **WHEN** qualquer imagem é construída
- **THEN** o contexto exclui, pelo `.dockerignore`, `.env`, chaves JSON, `platform/secrets/` e certificados
