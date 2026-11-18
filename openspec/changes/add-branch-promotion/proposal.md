# Proposal

## Why

O stack de hml e prod (`docker-compose.yml` na raiz, mais o `.env.example` e o script do Postgres que ele lê) existe só na branch `dev`. O Portainer vai sincronizar `atlas-hml` pela branch `hml` e `atlas-prod` pela branch de produção, então esses arquivos precisam chegar lá de forma controlada. Hoje `hml` está 26 commits atrás de `dev` e `main` está 98 commits atrás de `hml`; as proteções existem (check `ci-ok`), mas nada garante que o stack chegue íntegro, que `hml` e `main` não divirjam na definição e que ninguém edite o stack direto numa branch de implantação. O usuário também falou em "branch prod", que não existe: a produção hoje é a `main` (as tags `vX.Y` só valem nela).

## What Changes

- **Produção é a `main`, sem branch `prod` nova** (premissa registrada, coerente com o `release.yml`, com a regra de tag em `main` e com a proteção já existente). `atlas-hml` lê a branch `hml`; `atlas-prod` lê a `main`.
- **Promoção só por PR, na ordem `dev` → `hml` → `main`:** um job do CI recusa PR para `hml` que não venha de `dev` e PR para `main` que não venha de `hml`; os merges usam commit de merge (sem squash) para manter a ancestralidade entre as branches.
- **Validação do stack no CI:** um job `stack` roda em todo PR e push para `hml` e `main` e confere que `docker-compose.yml`, `.env.example` e `platform/postgres/init-databases.sh` existem, que `docker stack config` valida com as variáveis do exemplo para hml (tag `hml`) e para prod (tag `X.Y`), que não há tag `latest`, nem porta publicada no host, e que o Docker config e os secrets apontam para o que existe. Entra no `ci-ok`.
- **Proteção das branches de implantação:** `hml` e `main` exigem PR e `ci-ok`, bloqueiam push direto, force-push e exclusão, valem também para administradores; o CODEOWNERS cobre o stack e os arquivos de que ele depende. Os ajustes de configuração do GitHub são verificados por `gh api` e aplicados pelo usuário.
- **Produção só roda versão imutável:** o stack de prod usa `IMAGE_TAG` `X.Y`; o deploy de prod só é acionado por tag em `main` (já é assim no `_image.yml`) e o passo a passo traz a conferência de que nenhum serviço de prod usa a tag móvel `hml`.
- **Configuração do Portainer por ambiente** documentada: URL do repositório, referência da branch, caminho `docker-compose.yml`, sincronização por intervalo desligada, webhook do stack no Environment, e credencial de leitura apenas se o repositório deixar de ser público (guardada no Portainer, nunca no Git).
- **Primeira promoção executada:** PR `dev` → `hml` e depois `hml` → `main`, cada um com a aprovação do usuário.

## Capabilities

### New Capabilities
- `branch-promotion`: fluxo `dev` → `hml` → `main` por PR, com regra de origem, proteção das branches de implantação e produção só em versão imutável.
- `stack-validation`: verificação, no CI, de que o stack e os arquivos de que ele depende estão presentes e válidos nas branches de promoção.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Complementa add-hml-stack (stack, Portainer pelo GitHub) e add-hml-cicd-images (Environments e webhooks) sem repetir os requisitos delas. -->

## Impact

- `.github/workflows/ci.yml`: jobs `promocao` (só em PR) e `stack`, ambos no `ci-ok`.
- `platform/ci/check-stack.sh` (novo, roda também localmente) e `platform/ci/check-secrets.sh` (cobertura do `docker-compose.yml`, já tratada em `add-hml-stack` 2.8).
- `.github/CODEOWNERS`; configurações de proteção de `hml` e `main` e do merge no GitHub (feitas pelo usuário).
- `deploy/README.md`: configuração do Portainer por ambiente e conferência de produção.
- Branches `hml` e `main`: recebem o stack pelo fluxo de PR. Nada é publicado por este fluxo além do que o CI e os workflows de imagem já fazem.
