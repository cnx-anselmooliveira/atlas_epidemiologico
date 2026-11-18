# Design

## Context

Observado:

- Branches remotas: `dev`, `hml`, `main` (e `teste/portao-ci`). Não existe `prod`. `hml` está 26 commits atrás de `dev` (e 1 à frente, o commit de merge da promoção anterior); `main` está 98 commits atrás de `hml`.
- `hml` e `main` já têm proteção com o check obrigatório `ci-ok`; `hml` exige PR. O `ci.yml` roda em push e PR para `hml` e `main`. O `ci-ok` agrega os jobs `lint`, `ml-tests`, `ml-models-tests`, `images`, `dags`, `platform-e2e`, `frontend`, `backend`, `secrets` e `openspec`.
- `release.yml` só publica tag `vX.Y` de commit que está em `origin/main`; as imagens `X.Y` usam o mesmo critério. O `_image.yml` só aciona o webhook de produção em tag.
- O CODEOWNERS tem um único dono (`* @cnx-anselmooliveira`); com um só mantenedor, exigir aprovação de revisão bloquearia o próprio autor.
- O que o stack lê do repositório: o `docker-compose.yml` e, por Docker config, `platform/postgres/init-databases.sh`. As variáveis vêm do Portainer (modelo no `.env.example`).
- Premissas das mudanças vizinhas: `add-hml-stack` define o stack na raiz (`docker-compose.yml`), o Portainer lendo o repositório e o webhook do stack; `add-hml-cicd-images` define os Environments `hml` e `prod` e as imagens.

## Goals / Non-Goals

**Goals:**
- Garantir que o stack chegue a `hml` e `main` íntegro e só por PR.
- Impedir divergência entre as branches de implantação.
- Produção rodando apenas versão imutável.

**Non-Goals:**
- Criar uma branch `prod` ou um fluxo de hotfix separado (um hotfix passa por `dev` → `hml` → `main` como qualquer mudança).
- Exigir aprovação de revisor (um só mantenedor), CODEOWNERS com equipe, ou merge queue.
- Repetir a configuração do stack, dos Environments e dos webhooks, já definida nas outras duas mudanças.

## Decisions

1. **`prod` é a `main`.** Alternativa descartada: branch `prod` à frente da `main`. Ela acrescentaria um degrau de promoção, uma proteção a mais, e quebraria a regra atual "tag só em `main`" do `release.yml`, sem ganho para um stack lido por Portainer. Se um dia a produção precisar de cadência diferente da `main`, a mudança é só a referência no Portainer.

2. **Regra de origem no CI, não só na proteção.** O GitHub não restringe de qual branch sai um PR. O job `promocao` (só em `pull_request`) lê `github.base_ref` e `github.head_ref`: base `hml` exige head `dev`; base `main` exige head `hml`; qualquer outra combinação falha com mensagem que explica o fluxo. Roda sem checkout. PRs de fork não são tratados (o repositório não os usa para promoção).

3. **Merge com commit de merge, sem squash.** O squash cria commits novos em `hml` e `main` que não são ancestrais de `dev`, e o PR seguinte volta a listar tudo como diferença. O histórico atual já usa merge (`12088ab`). A configuração do repositório passa a oferecer só "Create a merge commit" para PRs (squash e rebase desligados), verificada por `gh api`.

4. **Um script único para validar o stack, `platform/ci/check-stack.sh`.** Roda no CI (job `stack`) e na máquina de quem altera o stack. Passos: (a) existência de `docker-compose.yml`, `.env.example` e dos arquivos referenciados em `configs.file`; (b) `docker stack config` com as variáveis do `.env.example` mais `ATLAS_ENV` e `IMAGE_TAG` de hml e de prod; (c) sobre a saída resolvida: nenhuma imagem `:latest`, nenhum `published:`, todo secret `external: true`, as imagens do projeto sob o prefixo configurado e as demais numa lista curta (`postgres`, `redis`). O `ubuntu-latest` já traz o Docker CLI. Alternativa descartada: só `docker compose config`, que ignora `deploy:`, `configs` e `secrets` de Swarm.

5. **Produção em tag imutável por duas camadas.** (a) O webhook de produção só roda para tag (já é assim); (b) o passo a passo de produção traz a conferência `docker service ls` mostrando só tags `X.Y`. Não há como o CI ler o valor de `IMAGE_TAG` no Portainer, por isso a verificação automática não pode ir além disso. O `check-stack.sh` valida que, com `IMAGE_TAG=1.0`, nenhum serviço fica com a tag `hml`, o que pega um valor fixo de tag colocado no arquivo.

6. **Proteção como configuração verificada por script, aplicada pelo usuário.** `gh api repos/.../branches/<b>/protection` lista o estado; uma tabela no README diz o que precisa estar ligado (PR, `ci-ok`, sem push direto nem force-push nem exclusão, incluindo administradores, sem exigir aprovação). Aplicar a mudança exige permissão de administrador e é feita pelo usuário; o assistente só verifica e mostra o diff.

7. **CODEOWNERS para o stack.** As linhas do stack, do exemplo de variáveis, do script do Postgres e de `deploy/` apontam para o mantenedor. Com um só dono isso não muda quem aprova, mas deixa o pedido de revisão explícito e prepara a entrada de mais pessoas.

8. **Portainer: dois stacks, mesma definição.** `atlas-hml` (`refs/heads/hml`) e `atlas-prod` (`refs/heads/main`), ambos com caminho `docker-compose.yml`, sincronização por intervalo desligada e o webhook do stack no Environment do ambiente (definido em `add-hml-cicd-images` e `add-hml-stack`). Repositório público: sem credencial. Se virar privado, um token de leitura entra na autenticação do repositório dentro do Portainer, nunca no Git.

9. **Primeira promoção.** `dev` → `hml` leva os 26 commits pendentes; `hml` → `main` leva tudo o que `main` ainda não tem (98 commits mais os da primeira promoção). Esse segundo PR é grande e toca o código de produção do site antigo: a revisão e o merge ficam com o usuário, e a tag de versão (`v0.1` ou outra) é decisão dele depois do merge.

## Risks / Trade-offs

- **`main` muito atrás:** o primeiro PR para `main` mistura muitas mudanças de uma vez. Mitigação: o CI completo roda no PR, e a lista de commits é revisada antes do merge; o deploy de produção não acontece até haver tag.
- **Um só mantenedor:** sem aprovação de revisão, a barreira é o CI e a regra de origem, não uma segunda pessoa. Aceito conscientemente.
- **A regra de origem pode atrapalhar um conserto urgente em `main`:** o conserto passa por `dev` e `hml`. Para emergência, o administrador pode desligar a proteção temporariamente; fica registrado como exceção manual.
- **`docker stack config` no CI depende do Docker CLI do runner:** é estável no `ubuntu-latest`; se faltar, o job falha em vez de passar em silêncio.
- **O job `stack` valida o arquivo, não o ambiente real:** variáveis erradas no Portainer só aparecem no deploy. O teste em Swarm local da `add-hml-stack` e a conferência de produção cobrem o resto.
