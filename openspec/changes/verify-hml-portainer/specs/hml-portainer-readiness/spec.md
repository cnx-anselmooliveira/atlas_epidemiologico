# Spec Delta

## Purpose

Garantir que o stack de hml suba no Portainer a partir da branch `hml` e que quem opera saiba preparar a VPS, atualizar, conferir, diagnosticar e voltar atrás.

## ADDED Requirements

### Requirement: Pré-requisitos da VPS verificáveis
O `deploy/README.md` SHALL listar os pré-requisitos do primeiro deploy, cada um com o comando que o confere: Swarm ativo, versões mínimas do Docker e do Portainer, rede overlay externa `network_public`, Traefik com a entrada `websecure` e o resolvedor `letsencryptresolver`, Docker secrets `atlas_hml_*`, DNS dos hosts, imagens `:hml` no DockerHub e o webhook do stack.

#### Scenario: Primeiro deploy
- **WHEN** alguém percorre a lista antes de criar o stack
- **THEN** cada item tem um comando cujo resultado diz se está pronto, e o que falta fica claro antes do deploy

### Requirement: Compatibilidade com o Portainer verificada
O stack SHALL ser criado pelo repositório em um Portainer real e SHALL ficar com todos os serviços no estado esperado, cobrindo o `configs` com `file:` relativo lido do clone do Git, o `airflow-init` como job de execução única, as variáveis obrigatórias do ambiente do stack, os secrets e a rede externos, a restrição de posicionamento e o usuário do Airflow.

#### Scenario: Stack criado pelo repositório
- **WHEN** o stack é criado no Portainer a partir do repositório, com a referência da branch e o caminho `docker-compose.yml`
- **THEN** o Portainer implanta sem erro de arquivo, de variável ou de secret e os serviços chegam ao estado esperado

#### Scenario: Variável obrigatória ausente
- **WHEN** o stack é criado sem `IMAGE_TAG`
- **THEN** o Portainer recusa o deploy com a mensagem da variável obrigatória

### Requirement: Atualização e commit conferido
O `deploy/README.md` SHALL descrever como atualizar o stack depois de uma mudança do arquivo (redeploy pelo Portainer ou pelo webhook do stack) e como confirmar que o Portainer está no commit esperado, comparando o commit exibido no stack com o da branch no GitHub.

#### Scenario: Arquivo mudou em hml
- **WHEN** um commit altera o `docker-compose.yml` em `hml`
- **THEN** o redeploy aplica a mudança e o commit exibido no Portainer passa a ser o da cabeça de `hml`

### Requirement: Diagnóstico e rollback
O `deploy/README.md` SHALL trazer o diagnóstico por serviço (estado e erro das tarefas, logs, secrets e variáveis) e o rollback: o automático do Swarm nas atualizações (`failure_action: rollback`) e o manual, redeployando o stack em um commit anterior pela referência do repositório.

#### Scenario: Deploy falhou
- **WHEN** um serviço não fica saudável depois do redeploy
- **THEN** o roteiro leva do estado do serviço à causa e permite voltar ao commit anterior sem perder os volumes

### Requirement: Nome do arquivo
O caminho do arquivo informado ao Portainer SHALL ser `docker-compose.yml`, o mesmo usado por CI, verificações e documentação.

#### Scenario: Compose path
- **WHEN** o stack é criado
- **THEN** o campo Compose path é `docker-compose.yml`
