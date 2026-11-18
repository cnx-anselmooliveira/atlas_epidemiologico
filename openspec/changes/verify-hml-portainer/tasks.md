# Tasks

## 1. Compatibilidade com o Portainer

- [x] 1.1 Subir um Portainer CE temporário no Swarm local (porta só em `127.0.0.1`, senha de teste descartável), criar a rede `network_public` e os secrets de teste (chave RSA descartável, nenhuma chave real) e preparar o ambiente do stack com os valores do `.env.example`; verificar com a API do Portainer respondendo e o endpoint do Swarm listado
- [x] 1.2 Criar o stack pelo repositório (API do Portainer: URL pública, referência `refs/heads/dev`, caminho `docker-compose.yml`, imagens `:local`) e conferir os pontos de verificação: `configs.file` relativo resolvido, `airflow-init` concluído como job, secrets e rede externos encontrados, restrição de posicionamento aceita e usuário `50000:0`; verificar com `docker stack ps` mostrando os serviços no estado esperado (o backend só com a chave real)
- [x] 1.3 Criar o mesmo stack sem `IMAGE_TAG` e conferir que o Portainer recusa com a mensagem da variável obrigatória; verificar a resposta da API
- [x] 1.4 Fazer um commit novo em `dev`, acionar o webhook do stack e conferir que o Portainer refaz o deploy e passa a exibir o commit novo; verificar comparando o commit do stack com `git ls-remote` da branch
- [x] 1.5 Apontar a referência para um commit anterior, redeployar e conferir que a definição volta e os volumes permanecem; depois restaurar a referência para a branch; verificar o commit exibido e os volumes (`docker volume ls`)
- [x] 1.6 Se algum ponto falhar, corrigir o `docker-compose.yml` ou o `check-stack.sh`, registrar o motivo no design e repetir 1.2; verificar o `ci-ok` do PR com a correção
- [x] 1.7 Remover o Portainer temporário, o stack, os secrets, a rede, os volumes e os dados de teste, deixando o Swarm local como estava; verificar com `docker stack ls`, `docker secret ls`, `docker volume ls` e `docker ps`

## 2. Pré-requisitos e roteiro no README

- [x] 2.1 Escrever em `deploy/README.md` a seção "Pré-requisitos da VPS" (Swarm, versões mínimas do Docker e do Portainer verificadas em 1.2, `network_public`, Traefik com `websecure` e `letsencryptresolver`, secrets `atlas_hml_*`, DNS dos hosts, imagens `:hml` e webhook), cada item com o comando que o confere; verificar executando os comandos que dá para rodar localmente e conferindo os nomes contra o `docker-compose.yml` e o `.env.example`
- [x] 2.2 Escrever a seção "Atualizar, conferir, diagnosticar e voltar atrás": redeploy manual e pelo webhook, conferência do commit (`git ls-remote` contra o commit do Portainer), diagnóstico por serviço e rollback automático e manual (referência para um commit anterior, `docker service rollback` como emergência); verificar que cada passo foi exercitado em 1.4 e 1.5 e que os comandos existem
- [x] 2.3 Registrar a premissa do nome `docker-compose.yml` (Compose path) no README e conferir que nenhum documento cita `docker-compose.yaml`; verificar com `git grep`

## 3. Fechamento com as mudanças vizinhas

- [ ] 3.1 Depois do merge do PR #4 (`add-branch-promotion` 5.1, com a aprovação do usuário), conferir que a branch `hml` tem `docker-compose.yml`, `.env.example` e `platform/postgres/init-databases.sh` (`git ls-tree origin/hml`) e repetir 1.2 e 1.3 com `refs/heads/hml`; verificar o stack subindo a partir de `hml`
- [ ] 3.2 Entregar ao usuário a lista final para a VPS (pré-requisitos, valores a preencher, webhook) e apontar para `add-hml-stack` 6.3 e `add-branch-promotion` 5.3, que executam a criação do stack real; verificar que as tarefas citadas continuam abertas e coerentes com este roteiro
