# Spec Delta

## Purpose

Levar o que foi promovido para `hml` até o Portainer da VPS sem passo manual além da criação inicial dos stacks, e sem cruzar hml com produção.

## ADDED Requirements

### Requirement: Webhooks por ambiente
A atualização do Portainer SHALL usar webhooks guardados como secrets de GitHub Environments: `hml` para pushes em `hml` e `prod` para tags de versão. Um push em `hml` SHALL nunca chamar o webhook de `prod`. O ambiente `prod` SHALL poder exigir aprovação. Sem webhook, a imagem SHALL ser publicada e o job SHALL registrar que o deploy não foi acionado.

#### Scenario: Push em hml
- **WHEN** a imagem `backend:hml` é publicada
- **THEN** o webhook do ambiente `hml` é chamado e o do ambiente `prod` não

#### Scenario: Versão
- **WHEN** a tag `v1.0` é publicada por um commit de `main`
- **THEN** o job aguarda a aprovação do ambiente `prod` e só então chama o webhook de produção

### Requirement: Stacks versionados sem valores
`deploy/` SHALL conter os stacks `app` (site, API e Redis) e `platform` (Postgres, MLflow e Airflow) com referências `${VARIAVEL}` e Docker secrets, nunca valores. Nenhum stack SHALL usar tag `latest` por padrão: a tag SHALL ser variável obrigatória.

#### Scenario: Tag não informada
- **WHEN** o stack é criado sem `BACKEND_TAG`
- **THEN** o Portainer recusa o stack com a mensagem de variável obrigatória

#### Scenario: Leitura das figuras
- **WHEN** o stack `app` sobe com a service account de leitura
- **THEN** o backend recebe o bucket e o prefixo das figuras por variável de stack e o PNG de uma figura é servido

### Requirement: Inventário de credenciais
`deploy/README.md` SHALL listar cada credencial com nome, onde é criada, quem a usa, para qual ambiente e como rotacionar, e SHALL trazer o passo a passo para DockerHub, GitHub Environments, webhooks do Portainer, Docker secrets e Connection do Airflow.

#### Scenario: Nova pessoa configura hml
- **WHEN** alguém segue o passo a passo do zero
- **THEN** consegue criar todos os secrets, variáveis e stacks sem consultar outro documento

### Requirement: Barreira contra credencial em `deploy/`
O job `secrets` SHALL falhar se um arquivo de `deploy/` tiver valor literal em campo de credencial (senha, token, chave, URL de webhook) em vez de referência a variável ou secret.

#### Scenario: Senha digitada no stack
- **WHEN** um commit coloca `POSTGRES_PASSWORD: abc123` em `deploy/platform.stack.yml`
- **THEN** o job `secrets` falha apontando o arquivo e a linha
