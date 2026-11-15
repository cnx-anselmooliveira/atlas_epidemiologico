# Design

## Context

- **Repositório:** `cnx-anselmooliveira/atlas_epidemiologico`, **público**, com as branches `dev`, `hml` e `main`. Ainda não há `README.md`, `LICENSE` nem `.github/` na raiz. Já existem READMEs por componente (`ml/`, `airflow/`, `infra/mlflow/`, `platform/`, `frontend/`) e documentos em `docs/referencias/`.
- **Referência visual:** o README do projeto *curral*, com quatro badges no topo: ci, release, docker pulls e license.
- **Peças das quais os badges dependem, ainda planejadas:**
  - `ci.yml`: `add-ci-test-pipeline`;
  - imagens no DockerHub: módulo 6 da `add-ml-platform`;
  - tags `vX.Y`: `release-promotion`.
- **Decisões do usuário:** licença MIT; todos os arquivos em português.

## Goals / Non-Goals

**Goals:**
- Arquivos de comunidade reconhecidos pelo GitHub: o *Community Standards* da aba Insights fica completo.
- Badges que passam a funcionar sozinhos quando o CI, as imagens e as releases existirem, sem editar o README de novo.
- Release reproduzível a partir da tag, sem passos manuais além de criar a tag.

**Non-Goals:**
- Versionamento semântico automático (release-please / semantic-release). A versão é decidida por quem cria a tag.
- Assinatura de releases e imagens (cosign) e SBOM. Ficam para quando houver usuários externos das imagens.

## Decisions

### 1. Badges
```markdown
# Atlas Epidemiológico da Dengue

[![ci](https://github.com/cnx-anselmooliveira/atlas_epidemiologico/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cnx-anselmooliveira/atlas_epidemiologico/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/cnx-anselmooliveira/atlas_epidemiologico)](https://github.com/cnx-anselmooliveira/atlas_epidemiologico/releases)
[![docker](https://img.shields.io/docker/pulls/anselmomendes/atlas-epidemiologia-ml)](https://hub.docker.com/r/anselmomendes/atlas-epidemiologia-ml)
[![license](https://img.shields.io/github/license/cnx-anselmooliveira/atlas_epidemiologico)](LICENSE)
```
- O badge de CI usa `?branch=main`: mostra o estado de produção, não o do último PR.
- A imagem do badge Docker é a de treino (`atlas-epidemiologia-ml`), o artefato central do projeto hoje. Quando o site existir, ela pode virar a do backend.
- Badges de shields.io em vez de imagens locais: o estado fica sempre atualizado e o repositório não guarda binários.

### 2. Estrutura do README
1. Título + badges + uma frase do que é.
2. **Sobre**: o objetivo científico (impressão digital ambiental, nicho ecológico do *Aedes*, previsão de incidência) e o estado atual.
3. **Arquitetura**: um diagrama **Mermaid**, que o GitHub renderiza nativamente, com fontes → BigQuery (raw/bronze/silver/gold, dbt) → Airflow/MLflow → API/site.
4. **Começo rápido**: os comandos do `platform/dev.ps1` e os endereços locais.
5. **Estrutura do repositório**: tabela de pastas com link para o README de cada uma.
6. **Fluxo de desenvolvimento**: dev → hml → main, tags `dev`/`hml`/`X.Y`, link para o `CONTRIBUTING.md`.
7. **Dados**: as fontes (SINAN, SIVIGILA, MINSA, SNVS, OBSALUD, OPAS) e o aviso de que os dados não são redistribuídos e seguem os termos das fontes.
8. **Como citar**: aponta para `CITATION.cff`, que o GitHub mostra como "Cite this repository".
9. **Licença** e links para conduta e segurança.

### 3. Licença
O texto integral da MIT (SPDX `MIT`), na forma exata do choosealicense.com, para que o GitHub detecte a licença. A linha de copyright é `Copyright (c) 2026 <titular>`. O titular precisa ser confirmado com o usuário na tarefa 1.1; a proposta padrão é o nome dele, como mantenedor do projeto. A licença cobre código e documentação do repositório. Dados de terceiros não estão no repositório.

### 4. CONTRIBUTING, CODE_OF_CONDUCT e SECURITY
- **CONTRIBUTING.md:**
  - pré-requisitos: Docker Desktop, uv e Node 22;
  - ambiente: `platform/dev.ps1 up`;
  - testes: `uv run pytest` e `ruff`;
  - fluxo de branches e PR: alvo `dev`, depois `hml`, depois `main`;
  - commits por assunto (`feat`, `fix`, `docs`, `test`, `ci`, `chore`, `build`);
  - OpenSpec para mudanças de comportamento: `openspec-propose` → `apply` → `archive`;
  - o check `ci-ok` obrigatório;
  - como pedir revisão.
- **CODE_OF_CONDUCT.md:** Contributor Covenant 2.1, na tradução oficial em português, com o contato definido na tarefa 1.1. O padrão sugerido é um e-mail dedicado do projeto, para não expor o e-mail pessoal ou corporativo.
- **SECURITY.md:**
  - versões suportadas: a última `X.Y` e a branch `main`;
  - reporte em *Security → Report a vulnerability*, que é o *Private vulnerability reporting*;
  - prazos: confirmação em até 5 dias úteis, avaliação em até 15;
  - fora de escopo: o ambiente de dev local e as dependências de terceiros, que devem ser reportadas ao projeto de origem.

### 5. Modelos do GitHub
`.github/ISSUE_TEMPLATE/`:
- `bug.yml`: formulário com versão/branch, passos, esperado e observado, logs;
- `melhoria.yml`;
- `config.yml`: desliga issues em branco e aponta segurança para o reporte privado.

`.github/pull_request_template.md` traz o checklist:
- branch de destino;
- testes locais;
- commits por assunto;
- mudança OpenSpec vinculada;
- sem segredos.

`.github/CODEOWNERS`: `* @cnx-anselmooliveira`.

### 6. Releases (`.github/workflows/release.yml`)
Disparado por `push` de tags `v*`. Etapas:
1. **guard:** confirma que o commit da tag está em `origin/main` (`git merge-base --is-ancestor`); senão, falha.
2. **tests:** `uses: ./.github/workflows/ci.yml` (da `add-ci-test-pipeline`).
3. **images:** `uses:` o workflow de publicação da `add-ml-platform` com a tag `X.Y`. Até aquele módulo existir, este passo fica ausente, e o workflow traz um comentário indicando onde encaixá-lo.
4. **github-release:**
   - `gh release create vX.Y --verify-tag --generate-notes --notes-file images.md`;
   - o `images.md` lista os `docker pull …:X.Y` das imagens do projeto;
   - também move a seção `[Não lançado]` do `CHANGELOG.md` para a versão, por PR automático para `dev`. Esse movimento fica como tarefa manual documentada na primeira versão, para não complicar.

`.github/release.yml` define as categorias das notas automáticas por label (`novidade`, `correção`, `documentação`, `infra`) e põe tudo o que não tiver label em "Outras mudanças". O template de PR lembra de aplicar a label.

`CHANGELOG.md` segue o *Keep a Changelog* em português, com a seção `[Não lançado]` resumindo o que já está em `dev`: plataforma de ML, modelos de previsão em andamento e CI.

### 7. Metadados e verificação
- **Metadados:** `gh repo edit` com descrição, `--homepage https://dengue.contovisual.com.br` e tópicos (`dengue`, `epidemiologia`, `epidemiology`, `machine-learning`, `mlflow`, `airflow`, `dbt`, `bigquery`, `astro`).
- **Reporte privado de vulnerabilidade:** `gh api -X PUT repos/cnx-anselmooliveira/atlas_epidemiologico/private-vulnerability-reporting`.
- **Verificação de links:** um job `links` no `ci.yml` com o `lycheeverse/lychee-action` em modo `--offline` (só links relativos), cobrindo README e `*.md` da raiz. Ele é acrescentado ao `ci.yml` da `add-ci-test-pipeline`; se este módulo for implementado antes, a tarefa espera o `ci.yml` existir.
- **Community Standards:** conferidos em `gh api repos/…/community/profile`, que precisa retornar `health_percentage = 100`.

## Risks / Trade-offs

- **[Badges "quebrados" até o CI, as imagens e as releases existirem]** → é aceitável e fica explicado num comentário HTML no README. Nenhuma edição é necessária quando as peças chegarem.
- **[E-mail de contato do código de conduta ficar público]** → usar um e-mail dedicado do projeto, ou, temporariamente, o canal de reporte privado do GitHub. A decisão fica na tarefa 1.1.
- **[A MIT permite uso comercial e fechado do código]** → foi uma decisão consciente do usuário. Os dados de terceiros não estão no repositório.

## Migration Plan

1. Implementar em `dev` e promover por PR para `hml` e `main`. Os arquivos de comunidade só aparecem na página do repositório quando chegam à branch padrão (`main`).
2. A primeira Release sai junto com a `v1.0` da `add-ml-platform`, módulo 8.

## Open Questions

- Nome do titular do copyright e e-mail de contato do código de conduta (tarefa 1.1).
- Se o badge Docker deve mudar para a imagem do backend quando o site for publicado.
