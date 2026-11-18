# Proposal

## Why

O `README.md` da raiz é a porta de entrada do projeto e ficou para trás. Ele ainda diz que o site está "em reconstrução" e que a plataforma roda "localmente"; cita a Base dos Dados como fonte do SINAN (a fonte agora é o OpenDataSUS); não lista a pasta `backend/`; descreve `deploy/` como "em construção"; mostra só as portas do MLflow e do Airflow; tem um único badge do DockerHub (`ml`) e nada sobre previsão, imagens publicadas, CI/CD, stack de hml e prod, `.env` único ou regras de segurança. Quem chega ao repositório não consegue entender o que existe nem como rodar ou implantar. Além disso, várias mudanças em andamento (`add-hml-stack`, `add-hml-cicd-images`, `add-branch-promotion`) renomeiam arquivos e fixam o fluxo de promoção, e o README precisa refletir os nomes finais.

## What Changes

- **Reescrita do `README.md` da raiz** para três públicos, com o princípio de que o principal **resume e aponta** (não repete o que já está em `ml/`, `airflow/`, `backend/`, `frontend/`, `platform/`, `deploy/` e `infra/mlflow/`):
  - *Entender o projeto:* o que é, o que o site mostra (início, série histórica, mapa por UF, previsão com seis modelos e a documentação de cada um), as fontes de dados (SINAN pelo OpenDataSUS) e a arquitetura atualizada (BigQuery, dbt, Airflow, MLflow, API com Redis, site).
  - *Rodar localmente:* pré-requisitos, `.env.example` → `.env`, `./platform/dev.ps1`, portas de todos os serviços (MLflow, Airflow, API, site, Jupyter), como rodar os testes de cada parte.
  - *Implantar:* imagens no DockerHub (`frontend`, `backend`, `airflow`, `mlflow`, `ml`), fluxo `dev` → `hml` → `main` com tags, stack único `docker-compose.yml` da raiz no Portainer para hml e prod, onde entra cada credencial e links para `deploy/README.md` e `platform/README.md`.
- **Seção de segurança resumida:** nenhuma credencial no Git, segredos só no `.env` local, nas variáveis e Docker secrets do Portainer, nas Connections e Variables do Airflow e nos secrets do GitHub.
- **Seção sobre OpenSpec:** como as mudanças são planejadas (`openspec/`), com a lista das mudanças ativas.
- **Remoção de referências obsoletas** (DAG `atlas_ml_example_training`, `platform/.env`, `deploy/app.stack.yml`, os dois exemplos de variáveis antigos, "Base dos Dados", "em reconstrução", "em construção") e atualização dos badges.
- **Verificação automática** (`platform/ci/check-readme.sh`, no job `lint`): links relativos do README existem, termos obsoletos não voltam, e o README cita todas as pastas de primeiro nível relevantes.
- **Escrita em duas passadas:** o que já está decidido e verificado (site, API, DAGs, plataforma local, imagens, segurança) é escrito agora; as partes que dependem do que as outras mudanças ainda movem (caminho final do stack na raiz, regra de promoção, Environments e webhook) usam os nomes decididos e são reconferidas no fechamento.

## Capabilities

### New Capabilities
- `project-readme`: conteúdo, estrutura, fidelidade ao repositório e verificação automática do `README.md` principal.

### Modified Capabilities
<!-- Nenhuma spec principal existe em openspec/specs/. -->

## Impact

- `README.md` (reescrito) e, se necessário, ajustes pontuais de link em `CONTRIBUTING.md`.
- `platform/ci/check-readme.sh` (novo) e `.github/workflows/ci.yml` (passo no job `lint`).
- Nenhuma mudança de código de aplicação, de workflow de imagem ou de infraestrutura.
- Depende de: `add-hml-stack` (tarefas 2.7 e 2.8, o `docker-compose.yml` na raiz), `add-branch-promotion` (fluxo e proteção) e `add-hml-cicd-images` (Environments, webhook e publicação das imagens). A documentação só é fechada depois delas; o rascunho pode ser escrito já.
