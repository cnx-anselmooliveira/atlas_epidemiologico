# Design

## Context

Observado:

- `docker-compose.yml` (raiz) é Swarm: `configs` com `file: ./platform/postgres/init-databases.sh`, `airflow-init` com `mode: replicated-job` e `restart_policy` com `max_attempts`, secrets `atlas_${ATLAS_ENV}_*` externos, rede externa `network_public`, rótulos do Traefik com `entrypoints=websecure` e `tls.certresolver=letsencryptresolver` (convenção herdada do antigo `app.stack.yml` da VPS), restrição `node.role == ${PLACEMENT_ROLE:-manager}`, `user: "50000:0"` no Airflow, e `update_config`/`rollback_config` com `failure_action: rollback` em vários serviços.
- Validado até aqui: `docker stack config` (CI e local), `docker stack deploy` direto num Swarm local de um nó (Airflow, MLflow, Postgres, site e Redis saudáveis; backend só com a chave real). **Não** validado: o fluxo do Portainer (clone do Git, ambiente do stack, webhook).
- O `deploy/README.md` tem o passo a passo de criação do stack, os secrets e o primeiro boot, mas não tem pré-requisitos da VPS nem roteiro de atualização, conferência de commit, diagnóstico e rollback.
- A branch `hml` não tem o compose; o PR #4 está `CLEAN` e aguarda o merge (`add-branch-promotion` 5.1).
- O Docker local já está em modo Swarm (nó único). A API do Portainer permite criar o stack pelo repositório sem a interface.

## Goals / Non-Goals

**Goals:**
- Provar, num Portainer real, que o stack sobe pelo repositório e que o redeploy pelo webhook funciona.
- Deixar a preparação da VPS e a operação do stack documentadas com comandos.

**Non-Goals:**
- Recriar o passo a passo do stack, dos secrets e dos Environments (já em `deploy/README.md`).
- Mergear o PR #4 ou promover para `main` (é de `add-branch-promotion`).
- Testar com a chave real do backend e as imagens `:hml` na VPS (é de `add-hml-stack` 2.4, 5.1 e 6.3).
- Instalar ou configurar o Traefik e o DNS da VPS.

## Decisions

1. **Nome mantido: `docker-compose.yml`.** O usuário escreveu `.yaml`, mas renomear tocaria CI (`check-stack.sh`, `check-secrets.sh`, `ci.yml`), `.dockerignore`, CODEOWNERS e todos os documentos, sem ganho: o campo "Compose path" do Portainer aceita qualquer nome. Se o usuário preferir `.yaml`, a troca é mecânica e fica como mudança à parte.

2. **Verificar com um Portainer CE temporário no Swarm local.** `portainer/portainer-ce` com o socket do Docker, porta só em `127.0.0.1`, admin criado pela API (`/api/users/admin/init`), autenticação (`/api/auth`) e criação do stack Swarm pelo repositório (`/api/stacks/create/swarm/repository`) com o ID do Swarm do endpoint, URL do repositório público, referência `refs/heads/dev` (a `hml` só depois do merge), caminho `docker-compose.yml` e as variáveis do `.env.example`. Alternativa descartada: só ler a documentação do Portainer, porque os pontos de risco (caminho relativo do `configs`, `replicated-job`, interpolação de `${VAR:?}`) dependem do comportamento real. Alternativa descartada: subir o Portainer na VPS para testar, porque o primeiro erro ali custa um deploy em ambiente compartilhado.

3. **Imagens `:local` no teste do Portainer.** Evita baixar mais de 10 GB do DockerHub; o objetivo é o comportamento do Portainer, não o pull. O pull das imagens `:hml` e a chave real ficam para a VPS. Se o Portainer tentar resolver a imagem no registro, o teste usa o nome com o prefixo local e registra o comportamento.

4. **Pontos de verificação do Portainer** (cada um vira um passo do teste): (a) o `configs.file` relativo é resolvido a partir do clone; (b) o `airflow-init` roda como job e termina; (c) as variáveis obrigatórias vêm do ambiente do stack e a ausência de `IMAGE_TAG` recusa o deploy; (d) secrets e rede externos são encontrados; (e) o webhook do stack refaz o deploy depois de um commit novo e o Portainer passa a exibir o commit novo; (f) apontar a referência para um commit anterior e redeployar volta a definição e mantém os volumes.

5. **Pré-requisitos como lista com comando.** `docker info --format '{{.Swarm.LocalNodeState}}'`, `docker version --format '{{.Server.Version}}'`, `docker network inspect network_public --format '{{.Driver}} {{.Scope}}'`, `docker secret ls`, `dig +short <host>`, `docker manifest inspect anselmomendes/atlas-epidemiologia-<imagem>:hml`, e a conferência do Traefik (`docker service inspect traefik` ou o painel) de que a entrada `websecure` e o resolvedor `letsencryptresolver` existem. A versão mínima do Docker para `replicated-job` (20.10) e a do Portainer entram na lista depois de verificadas no teste.

6. **Como conferir o commit.** O Portainer mostra o commit do stack na página do stack (campo de Git); o comando de comparação é `git ls-remote https://github.com/cnx-anselmooliveira/atlas_epidemiologico refs/heads/hml`. O roteiro manda comparar os sete primeiros caracteres.

7. **Rollback em duas camadas.** Automático: `failure_action: rollback` desfaz uma atualização que não fica saudável. Manual: no Portainer, trocar a "Repository reference" para o hash do commit anterior (ou uma tag) e redeployar; volumes e secrets não mudam. `docker service rollback <serviço>` fica como recurso de emergência para um único serviço. Depois de voltar, a referência é restaurada para a branch.

8. **Diagnóstico por serviço.** Ordem do roteiro: `docker stack ps atlas-hml --no-trunc` (estado e erro de cada tarefa), `docker service logs <serviço> --tail 50`, conferir variável obrigatória faltando (mensagem do Portainer), secret inexistente (`docker secret ls`), rede inexistente, `PLACEMENT_ROLE` sem nó compatível, imagem sem tag publicada.

## Risks / Trade-offs

- **O Portainer local não é a VPS:** versão do Portainer, do Docker e do Traefik podem diferir. Mitigação: a lista de pré-requisitos pede as versões, e o primeiro deploy real (`add-hml-stack` 6.3) confirma.
- **Teste com `:local` não prova o pull do DockerHub:** pull de uma imagem de 10 GB só se mostra na VPS (tempo e disco). O README avisa.
- **Portainer temporário com acesso ao socket do Docker:** é um container privilegiado local. Mitigação: porta só em `127.0.0.1`, senha de teste descartável, removido (container, volume e dados) ao final do teste.
- **Se o teste revelar incompatibilidade,** a correção entra no `docker-compose.yml` (ou no `check-stack.sh`) dentro desta mudança, com o motivo registrado aqui, e passa pelo mesmo fluxo de PR.
