# Proposal

## Why

O stack de hml está pronto e validado no CI e num Swarm local, mas só existe em `dev`: a branch `hml` ainda não tem o `docker-compose.yml` (o PR #4 `dev` → `hml` está com todos os checks verdes e aguarda o merge). O usuário precisa que o arquivo esteja em `hml` para o Portainer criar o stack `atlas-hml` pelo GitHub. Mesmo com o arquivo lá, três coisas ainda não estão resolvidas e nenhuma das mudanças vizinhas as cobre: (1) a compatibilidade com o **Portainer** em si nunca foi testada (o teste local usou `docker stack deploy` direto); (2) não há lista dos **pré-requisitos da VPS** antes do primeiro deploy (Swarm, rede `network_public`, Traefik, DNS, secrets, imagens); (3) não há **roteiro operacional** para atualizar o stack quando o arquivo mudar, conferir que o Portainer leu o commit certo, diagnosticar uma falha e voltar atrás.

## What Changes

- **Premissa sobre o nome:** o arquivo continua `docker-compose.yml` (o usuário escreveu `.yaml`). CI, `check-stack.sh`, `check-secrets.sh`, `.dockerignore` e os documentos usam esse nome e o Portainer aceita qualquer caminho em "Compose path". A troca só acontece se o usuário pedir.
- **Pré-requisitos da VPS** no `deploy/README.md`, cada um com o comando que o confere: Swarm ativo e versão mínima do Docker e do Portainer, rede overlay externa `network_public`, Traefik com a entrada `websecure` e o resolvedor `letsencryptresolver`, Docker secrets `atlas_hml_*`, DNS dos cinco hosts, imagens `:hml` já publicadas no DockerHub e o webhook do stack.
- **Compatibilidade com o Portainer verificada de verdade:** subir um Portainer CE temporário contra o Swarm local, criar o stack pelo repositório (API do Portainer) e conferir o que o teste anterior não cobriu: `configs` com `file:` relativo lido do clone do Git, `mode: replicated-job` do `airflow-init`, variáveis obrigatórias `${VAR:?}` vindas do ambiente do stack, secrets e rede externos, restrição `node.role`, `user: 50000:0` e o redeploy pelo webhook do stack.
- **Roteiro operacional** no `deploy/README.md`: atualizar o stack depois de uma mudança do arquivo em `hml` (redeploy manual ou pelo webhook), como confirmar que o Portainer está no commit certo, diagnóstico por serviço e rollback (automático do Swarm e manual por commit anterior).
- **O que apenas aponta para as outras mudanças** (sem repetir): o merge do PR #4 e o PR `hml` → `main` (`add-branch-promotion` 5.1 a 5.3), a verificação com a chave real do backend e a criação do stack na VPS (`add-hml-stack` 2.4, 5.1 e 6.3), a conta de leitura do backend (`add-hml-cicd-images` 3.3).

## Capabilities

### New Capabilities
- `hml-portainer-readiness`: pré-requisitos da VPS, compatibilidade verificada com o Portainer e roteiro de atualização, conferência, diagnóstico e rollback do stack de hml.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. Complementa add-hml-stack, add-hml-cicd-images e add-branch-promotion. -->

## Impact

- `deploy/README.md`: duas seções novas (pré-requisitos da VPS; atualizar, conferir, diagnosticar e voltar atrás).
- Possível ajuste no `docker-compose.yml` ou no `check-stack.sh` se o teste com o Portainer revelar incompatibilidade (registrado no design).
- Um Portainer CE temporário e os recursos de teste no Swarm local, removidos ao final; nenhuma chave real.
- Depende do merge do PR #4 para a verificação final a partir da branch `hml`; o resto roda a partir de `dev`.
