# Spec Delta

## Purpose

Transformar cada versão de produção numa GitHub Release com notas legíveis, ligada às imagens Docker da mesma versão.

## ADDED Requirements

### Requirement: Release a partir da tag de versão
Toda tag `vX.Y` (ou `vX.Y.Z`) criada num commit de `main` SHALL gerar uma GitHub Release com o mesmo nome. Tags fora de `main` SHALL NOT gerar Release.

#### Scenario: Primeira versão
- **WHEN** a tag `v1.0` é criada num commit de `main`
- **THEN** existe a Release `v1.0` no GitHub
- **AND** o badge de release do README passa a mostrar `v1.0`

#### Scenario: Tag fora de main
- **WHEN** a tag `v1.1` é criada num commit que não está em `main`
- **THEN** nenhuma Release é criada e o workflow falha explicando o motivo

### Requirement: Notas geradas e categorizadas
As notas da Release SHALL ser geradas a partir dos pull requests e commits desde a versão anterior, agrupadas por categoria (novidades, correções, documentação, infraestrutura/CI). Elas SHALL incluir a lista das imagens Docker publicadas com a tag `X.Y`.

#### Scenario: Conteúdo das notas
- **WHEN** a Release `v1.0` é publicada
- **THEN** as notas trazem as categorias de mudanças e as linhas `docker pull anselmomendes/atlas-epidemiologia-<imagem>:1.0` de cada imagem

### Requirement: Changelog versionado
O repositório SHALL manter um `CHANGELOG.md` no formato *Keep a Changelog*, com uma seção `[Não lançado]` e uma seção por versão publicada, com data e link para a Release.

#### Scenario: Antes da primeira release
- **WHEN** ainda não há nenhuma versão publicada
- **THEN** o `CHANGELOG.md` tem apenas a seção `[Não lançado]`, com as mudanças acumuladas

### Requirement: Release só depois das imagens
A Release SHALL ser publicada somente depois de os testes do CI e a publicação das imagens `X.Y` terminarem com sucesso para aquele commit.

#### Scenario: Falha na publicação de imagem
- **WHEN** a publicação da imagem `1.0` falha
- **THEN** a Release `v1.0` não é criada
