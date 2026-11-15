# Spec Delta

## Purpose

Definir como o código vira imagem em cada ambiente e garantir que nada chegue a produção sem passar por desenvolvimento e homologação.

## ADDED Requirements

### Requirement: Branch e tag de imagem por ambiente
O CI SHALL publicar as imagens do projeto com uma tag por ambiente, derivada da origem do código:

| Origem | Tag publicada |
|---|---|
| push na branch `dev` | `dev` |
| push na branch `hml` | `hml` |
| tag git `vX.Y` (ou `vX.Y.Z`) em commit de `main` | `X.Y` (ou `X.Y.Z`) |

Pushes em outras branches e pull requests SHALL apenas validar e buildar, sem publicar.

#### Scenario: Push em dev
- **WHEN** um commit é enviado para a branch `dev` alterando `ml/`
- **THEN** a imagem `atlas-epidemiologia-ml:dev` é publicada no DockerHub

#### Scenario: Release de produção
- **WHEN** a tag git `v1.0` é criada num commit de `main`
- **THEN** a imagem `atlas-epidemiologia-ml:1.0` é publicada

### Requirement: Ordem de promoção
O código SHALL seguir `dev` → `hml` → `main`. A branch `hml` SHALL receber mudanças só por merge vindo de `dev`, e `main` só por merge vindo de `hml`. Uma tag de versão SHALL ser criada apenas em commit de `main`.

#### Scenario: Tag fora de main
- **WHEN** a tag `v1.1` é criada num commit que não está em `main`
- **THEN** o CI falha e nenhuma imagem `1.1` é publicada

#### Scenario: Merge direto de dev em main
- **WHEN** um pull request de `dev` para `main` é aberto
- **THEN** a verificação do CI falha indicando que `main` só aceita `hml`

### Requirement: Tags de versão imutáveis
Uma tag de versão já publicada (ex.: `1.0`) SHALL NOT ser sobrescrita. As tags `dev` e `hml` SHALL ser móveis.

#### Scenario: Republicar 1.0
- **WHEN** o CI tenta publicar `1.0` de novo e a tag já existe no DockerHub
- **THEN** o workflow falha sem sobrescrever a imagem

### Requirement: Implantação por ambiente
Após publicar `hml`, o CI SHALL atualizar as stacks de hml na VPS. Após publicar `X.Y`, o CI SHALL atualizar as stacks de prod. A tag `dev` SHALL NOT disparar implantação na VPS.

#### Scenario: Publicação de hml
- **WHEN** a imagem `atlas-epidemiologia-airflow:hml` é publicada
- **THEN** a stack do Airflow de hml é atualizada
- **AND** a stack de prod continua na versão anterior

### Requirement: Um commit por módulo
O desenvolvimento SHALL ser registrado em commits que correspondem cada um a um módulo concluído da lista de tarefas, com mensagem identificando o módulo.

#### Scenario: Módulo concluído
- **WHEN** todas as tarefas de um grupo da lista de tarefas estão concluídas e verificadas
- **THEN** existe um commit na branch `dev` cuja mensagem cita esse módulo
