# Tasks

## 1. Decisões pendentes e licença

- [x] 1.1 Confirmar com o usuário o titular do copyright da licença e o canal de contato do código de conduta (e-mail dedicado do projeto ou outro); registrar as respostas no design; verificar que nenhum e-mail pessoal ou corporativo entra em texto aberto sem autorização
- [x] 1.2 Criar `LICENSE` com o texto integral da MIT (formato do choosealicense.com) e `Copyright (c) 2026 <titular>`; verificar, depois que chegar a `main`, que `gh api repos/cnx-anselmooliveira/atlas_epidemiologico/license -q .license.spdx_id` retorna `MIT`
- [x] 1.3 Criar `CITATION.cff` (título, autores, licença MIT, URL do repositório, resumo); verificar com `cffconvert --validate` (via `uvx`)
- [x] 1.4 Commit em `dev` (`docs: licença MIT e citação`); verificar `git log -1 --stat`

## 2. README

- [x] 2.1 Criar `README.md` na raiz: título, os quatro badges (ci com `?branch=main`, release, docker pulls de `atlas-epidemiologia-ml`, license), sobre, diagrama Mermaid da arquitetura, começo rápido, estrutura de pastas com links, fluxo dev → hml → main, dados e fontes (sem redistribuição), como citar e licença; verificar a renderização com `gh markdown-preview` ou na página da branch `dev`
- [x] 2.2 Conferir todos os links relativos do README e dos `*.md` da raiz com `lychee --offline` (via container `lycheeverse/lychee`); verificar zero links quebrados
- [x] 2.3 Commit em `dev` (`docs: README do projeto com badges`); verificar `git log -1 --stat`

## 3. Arquivos de comunidade

- [x] 3.1 Criar `CONTRIBUTING.md` (pré-requisitos, ambiente, testes, fluxo de branches e PR, commits por assunto, OpenSpec, checks obrigatórios, revisão); verificar seguindo os passos de testes num clone limpo
- [x] 3.2 Criar `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1, tradução oficial em português, com o contato da tarefa 1.1); verificar que o texto corresponde à versão 2.1
- [x] 3.3 Criar `SECURITY.md` (versões suportadas, reporte privado em Security → Report a vulnerability, prazos de 5 e 15 dias úteis, fora de escopo) e ativar o reporte privado com `gh api -X PUT …/private-vulnerability-reporting`; verificar com `gh api …/private-vulnerability-reporting -q .enabled` = `true`
- [x] 3.4 Criar `.github/ISSUE_TEMPLATE/bug.yml`, `melhoria.yml`, `config.yml` (sem issue em branco; segurança → reporte privado), `.github/pull_request_template.md` (checklist) e `.github/CODEOWNERS`; verificar a sintaxe dos formulários abrindo "New issue" na branch padrão depois da promoção
- [x] 3.5 Commit por assunto em `dev` (`docs: guia de contribuição, código de conduta e política de segurança`; `chore(github): modelos de issue, PR e CODEOWNERS`); verificar `git log --oneline -2`

## 4. Releases

- [x] 4.1 Criar `CHANGELOG.md` (Keep a Changelog em português, seção `[Não lançado]` resumindo plataforma de ML, modelos de previsão e CI); verificar o formato das seções
- [x] 4.2 Criar `.github/release.yml` (categorias por label: novidade, correção, documentação, infra, outras) e as labels no repositório com `gh label create`; verificar com `gh label list`
- [ ] 4.3 Criar `.github/workflows/release.yml` (tag `v*` → guarda de `main` → `uses: ./.github/workflows/ci.yml` → espaço comentado para a publicação de imagens da `add-ml-platform` → `gh release create --verify-tag --generate-notes` com a lista de `docker pull …:X.Y`); verificar com `actionlint` e com uma tag de teste `v0.0.0-teste` num commit fora de `main` sendo recusada (apagar a tag depois)
- [ ] 4.4 Commit por assunto em `dev` (`docs: changelog`; `ci: publicação de releases a partir da tag`); verificar `git log --oneline -2`

## 5. Metadados, verificação e promoção

- [ ] 5.1 Configurar descrição, site e tópicos com `gh repo edit`; verificar com `gh repo view --json description,homepageUrl,repositoryTopics`
- [ ] 5.2 Adicionar o job `links` (lychee `--offline`) ao `ci.yml` (requer a `add-ci-test-pipeline` implementada); verificar com `actionlint` e o job verde no PR
- [ ] 5.3 Promover por PR `dev → hml → main` e conferir na página do repositório os badges, o "Cite this repository", a licença MIT detectada e `gh api repos/…/community/profile -q .health_percentage` = `100`
- [ ] 5.4 Commit dos ajustes, se houver, em `dev` (`docs: ajustes da governança após promoção`); verificar `git log -1`

## Workflow follow-up

- Publicar a primeira Release junto com a `v1.0` (módulo 8 da `add-ml-platform`) e arquivar esta mudança.
