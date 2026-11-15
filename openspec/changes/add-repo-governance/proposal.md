# Proposal

## Why

O repositório `cnx-anselmooliveira/atlas_epidemiologico` passou a ser **público**, mas ainda não diz o que é, sob quais termos pode ser usado, como contribuir nem como reportar uma vulnerabilidade. Não há README na raiz, licença, guia de contribuição, código de conduta nem política de segurança. Sem licença, o código é "todos os direitos reservados" e ninguém pode reutilizá-lo legalmente, o que vai contra o objetivo acadêmico e aberto do Atlas. O formato de referência é o do projeto *curral*: README com badges de CI, release, imagens Docker e licença no topo.

## What Changes

- **`README.md` na raiz**, em português, com:
  - **badges no topo:** CI (`ci.yml`), última release, pulls do DockerHub da imagem principal e licença;
  - **corpo:** o que é o Atlas, arquitetura em uma figura, como rodar a plataforma local, estrutura de pastas, fluxo dev → hml → main, links para a documentação de cada componente e as fontes de dados com a forma de citar.
- **`LICENSE` MIT** na raiz, com o titular do copyright e o ano.
- **`CONTRIBUTING.md`**: como preparar o ambiente, rodar os testes, o fluxo de branches e de pull requests, commits por assunto, mudanças planejadas com OpenSpec e o que o CI exige.
- **`CODE_OF_CONDUCT.md`**: Contributor Covenant 2.1 em português, com o canal de contato para denúncias.
- **`SECURITY.md`**: versões suportadas, reporte privado pelo *Private vulnerability reporting* do GitHub (sem e-mail público), prazos de resposta e o que está fora de escopo.
- **Releases no GitHub (para o futuro, preparado agora):** toda tag `vX.Y` em `main`, a mesma que publica as imagens `X.Y` (`release-promotion`), gera uma GitHub Release com notas automáticas a partir dos commits. Junto vêm um `CHANGELOG.md` e a configuração das categorias de notas.
- **Arquivos de apoio do GitHub:** templates de issue (bug, ideia) e de pull request com o checklist do fluxo, e `CODEOWNERS`.
- **Metadados do repositório:** descrição, tópicos e site no GitHub; ativar o *Private vulnerability reporting*.

## Capabilities

### New Capabilities
- `repository-governance`: o que o repositório público expõe a quem chega: identificação, licença, regras de contribuição e conduta, canal de segurança e modelos de issue e PR.
- `release-publishing`: como uma versão vira GitHub Release, com notas, changelog e vínculo com as imagens `X.Y`.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/. release-publishing complementa release-promotion (add-ml-platform, ainda não arquivada): a mesma tag vX.Y que publica imagens passa a publicar a Release. -->

## Impact

- **Arquivos novos na raiz:** `README.md`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` e `CHANGELOG.md`.
- **Arquivos novos em `.github/`:** `release.yml`, `ISSUE_TEMPLATE/`, `pull_request_template.md`, `CODEOWNERS` e `workflows/release.yml`.
- **Badges com estado inicial vazio:**
  - "release" mostra *no releases* até a primeira tag `v1.0`;
  - "docker pulls" mostra *repo not found* até a imagem existir no DockerHub (módulo 6 da `add-ml-platform`);
  - "ci" fica vermelho ou cinza até o `ci.yml` da `add-ci-test-pipeline` existir.
  - Isso é aceitável e está documentado. Os badges passam a funcionar sozinhos quando essas peças chegarem.
- **GitHub:** configurações via `gh` (descrição, tópicos, *Private vulnerability reporting*).
- **Fora de escopo:**
  - site de documentação (GitHub Pages);
  - versão em inglês;
  - DCO/CLA para contribuições;
  - licenças diferentes para dados e documentação (tudo fica em MIT).
  - Os dados de terceiros (SINAN, OPAS etc.) não são redistribuídos no repositório e seguem os termos das fontes, o que fica dito no README.
