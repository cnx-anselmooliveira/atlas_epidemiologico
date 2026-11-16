# Spec Delta

## Purpose

Dar ao repositório público do Atlas uma porta de entrada clara: o que é, como usar, sob qual licença, como contribuir, como se comportar e como reportar problemas de segurança.

## ADDED Requirements

### Requirement: README com badges de estado
A raiz SHALL ter um `README.md` em português que comece pelo nome do projeto e por badges de:
- estado do CI;
- última release;
- pulls da imagem Docker principal;
- licença.

Cada badge SHALL levar a página correspondente (execuções do workflow, releases, repositório no DockerHub e arquivo de licença).

#### Scenario: Visitante abre o repositório
- **WHEN** alguém abre a página do repositório no GitHub
- **THEN** vê o nome do projeto e os quatro badges antes de qualquer outro conteúdo
- **AND** clicar no badge de CI abre as execuções do workflow `ci.yml`

### Requirement: Conteúdo mínimo do README
O README SHALL explicar:
- o objetivo do Atlas;
- a arquitetura (BigQuery, dbt, Airflow, MLflow, API e site);
- como subir a plataforma local em poucos comandos;
- a estrutura de pastas com links para o README de cada componente;
- o fluxo dev → hml → main;
- as fontes de dados, com o aviso de que dados de terceiros seguem os termos das fontes;
- como citar o projeto.

Todos os links relativos SHALL apontar para arquivos existentes.

#### Scenario: Link quebrado
- **WHEN** o README contém um link relativo para um arquivo que não existe
- **THEN** a verificação de links do CI falha

### Requirement: Licença aberta
A raiz SHALL ter um arquivo `LICENSE` com o texto integral da licença MIT, o ano e o titular do copyright. O GitHub SHALL reconhecer a licença como MIT.

#### Scenario: Reconhecimento pelo GitHub
- **WHEN** a API do GitHub é consultada sobre a licença do repositório
- **THEN** retorna `spdx_id = MIT`

### Requirement: Guia de contribuição
O repositório SHALL ter um `CONTRIBUTING.md` que descreva:
- preparação do ambiente;
- como rodar os testes;
- o fluxo de branches (`dev` → `hml` → `main` por pull request);
- o padrão de commits por assunto;
- o uso do OpenSpec para mudanças planejadas;
- os checks exigidos para merge.

#### Scenario: Novo contribuidor
- **WHEN** alguém segue o `CONTRIBUTING.md` do início
- **THEN** consegue rodar os testes do pacote `ml` e abrir um pull request para `dev` com o template preenchido

### Requirement: Código de conduta
O repositório SHALL ter um `CODE_OF_CONDUCT.md` baseado no Contributor Covenant 2.1, em português, com um canal de contato para denúncias que não exponha dados pessoais do mantenedor em texto aberto.

#### Scenario: Denúncia
- **WHEN** alguém precisa reportar um comportamento inadequado
- **THEN** o código de conduta indica o canal de contato e o compromisso de confidencialidade

### Requirement: Política de segurança com reporte privado
O repositório SHALL ter um `SECURITY.md` com as versões suportadas, as instruções de reporte privado pelo recurso *Private vulnerability reporting* do GitHub, os prazos de resposta e o escopo. O reporte privado SHALL estar ativado no repositório.

#### Scenario: Vulnerabilidade encontrada
- **WHEN** alguém encontra uma vulnerabilidade
- **THEN** o `SECURITY.md` o orienta a usar "Report a vulnerability" na aba Security, sem abrir issue pública
- **AND** o botão está disponível no repositório

### Requirement: Modelos de issue e de pull request
O repositório SHALL ter:
- modelos de issue para reporte de bug e para proposta de melhoria;
- um modelo de pull request com checklist (testes locais, commits por assunto, mudança OpenSpec quando aplicável, branch de destino correta);
- um `CODEOWNERS` que atribua o mantenedor como revisor.

#### Scenario: Abrir pull request
- **WHEN** alguém abre um pull request
- **THEN** a descrição já vem preenchida com o checklist do modelo
