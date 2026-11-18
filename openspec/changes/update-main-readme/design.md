# Design

## Context

Observado no `README.md` atual (112 linhas) e no repositório:

- Seções existentes: Sobre, Arquitetura (diagrama Mermaid), Começo rápido, Estrutura do repositório, Fluxo de desenvolvimento, Dados, Como citar, Licença.
- Desatualizado: "Estado atual" (site em reconstrução, pipeline em migração), fonte do SINAN (Base dos Dados; agora OpenDataSUS), tabela da estrutura sem `backend/` e com `deploy/` "em construção", "Começo rápido" só com MLflow e Airflow (o compose de desenvolvimento também sobe API :8000, site :4321 e Redis), um único badge do DockerHub (`ml`), nenhuma menção a previsão, imagens, CI/CD, stack de hml e prod, `.env` único ou segurança.
- Cada pasta já tem README próprio: `ml/` (126 linhas), `airflow/` (86), `backend/` (78), `frontend/` (121), `platform/` (121), `deploy/` (112). O principal não deve repeti-los.
- O CI tem o job `lint`; a verificação de documentação pode entrar nele sem novo job.
- As mudanças vizinhas fixam nomes que o README citará: `docker-compose.yml` na raiz (`add-hml-stack`, tarefas 2.7 e 2.8 ainda por fazer), `.env.example` único (já feito), Environments `hml` e `prod` com `PORTAINER_WEBHOOK_STACK` (`add-hml-cicd-images`, já no workflow), promoção `dev` → `hml` → `main` por PR (`add-branch-promotion`).

## Goals / Non-Goals

**Goals:**
- Um README curto (alvo: cerca de 150 linhas) que serve a três públicos e aponta para os demais.
- Fiel ao repositório: comandos e links conferidos, sem referência obsoleta.
- Uma verificação automática barata que impeça a volta do desatualizado.

**Non-Goals:**
- Reescrever os READMEs das pastas ou os documentos de `docs/`.
- Gerar o README a partir do código ou criar um site de documentação.
- Traduzir o README para outro idioma.

## Decisions

1. **Estrutura em três blocos, na ordem do leitor.** (1) *O que é* (resumo, o que o site mostra, dados, arquitetura); (2) *Rodar localmente* (pré-requisitos, `.env`, `dev.ps1`, portas, testes); (3) *Implantar* (imagens, fluxo e tags, stack da raiz, segredos); depois *Estrutura do repositório*, *Segurança*, *OpenSpec*, *Como citar*, *Licença*. O sumário no topo é uma lista de âncoras de uma linha.

2. **Resumir e apontar.** Cada pasta aparece numa tabela com uma frase e o link. Procedimentos longos (bucket GCS, rede corporativa, Portainer passo a passo, rotação de segredos) ficam nos READMEs das pastas; o principal só diz onde estão. Alternativa descartada: um README gigante com tudo, que envelhece mais rápido e duplica o que `platform/` e `deploy/` já dizem.

3. **Duas passadas.** Primeira passada (pode ser feita já): tudo o que está pronto e verificado. Os nomes ainda em movimento (`docker-compose.yml` na raiz, regra de origem de PR, secrets dos Environments) entram com os nomes **já decididos**. Segunda passada, no fechamento: depois de `add-hml-stack` 2.7/2.8, `add-branch-promotion` 1 e 2 e a primeira publicação das imagens, rodar a verificação e reler os links e comandos contra o repositório real. Alternativa descartada: esperar tudo terminar para começar, porque a maior parte do texto não depende delas.

4. **Badges.** Manter `ci`, `release` e `license`; trocar o badge único de DockerHub por um por imagem publicada (`frontend`, `backend`, `airflow`, `mlflow`, `ml`) ou por um link para o namespace, evitando uma fileira longa. Os badges de release e DockerHub continuam vazios até a primeira tag `vX.Y` e a primeira publicação; o comentário no topo do arquivo explica isso e é mantido.

5. **Comandos testados antes de entrar.** Cada bloco de comando do README é executado na máquina (ou pelo CI quando possível): `dev.ps1 up/status`, portas, `pytest` de `ml/` e `backend/`, `npm test` e `npm run check` de `frontend/`, e os comandos do dbt só se já documentados no README do airflow (então apenas apontados).

6. **`platform/ci/check-readme.sh` no job `lint`.** Três conferências sem rede: (a) todo link relativo `](caminho)` do README existe (ignora URLs e âncoras); (b) lista de termos obsoletos (`atlas_ml_example_training`, `platform/.env`, `app.stack.yml`, `Base dos Dados`, `em reconstrução`, `em construção`) ausente; (c) cada pasta de uma lista fixa (`ml`, `airflow`, `backend`, `frontend`, `infra/mlflow`, `platform`, `deploy`, `docs`, `openspec`) é citada. Alternativa descartada: verificador de links com rede (lychee), por depender de internet e gerar falso positivo em badges.

7. **Segurança em uma seção curta** com uma tabela "tipo de segredo → onde entra" (`.env` local, variável de stack, Docker secret, Connection do Airflow, secret do GitHub) e links para `SECURITY.md` e `deploy/README.md`. Sem repetir o inventário completo.

8. **Seção OpenSpec** descreve o fluxo (`proposta → aplicar → arquivar`) e remete a `openspec/changes/`; a lista de mudanças ativas não é copiada (envelhece), só o comando `openspec list`.

## Risks / Trade-offs

- **Envelhecer de novo:** o README pode divergir quando as pastas mudam. A verificação automática pega links e termos, não a verdade dos comandos; por isso o fechamento inclui executar os comandos e a convenção de apontar em vez de copiar.
- **Nomes ainda em movimento:** se o `docker-compose.yml` da raiz mudar de nome ou lugar, o README precisa de um ajuste; a verificação de links falha e avisa.
- **Badges vazios** até a primeira versão e a publicação das imagens podem confundir; o comentário no arquivo e uma frase na seção de implantação explicam.
- **Tamanho:** o limite de cerca de 150 linhas obriga a cortar; o que sobrar vai para os READMEs das pastas, não para o principal.
