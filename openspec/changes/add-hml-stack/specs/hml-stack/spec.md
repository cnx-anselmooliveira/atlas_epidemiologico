# Spec Delta

## Purpose

Subir o Atlas inteiro na VPS, em hml e em produção, a partir das imagens publicadas, com a mesma definição e só as variáveis mudando.

## ADDED Requirements

### Requirement: Stack único por ambiente
O repositório SHALL ter um único arquivo `deploy/atlas.stack.yml` em formato Swarm com os serviços `postgres`, `mlflow`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-triggerer`, `backend`, `frontend` e `redis`. O arquivo SHALL usar só imagens do DockerHub escolhidas por variável de tag, sem `build`, sem volume de código e sem portas publicadas no host. A tag SHALL ser variável obrigatória e nunca `latest`.

#### Scenario: Mesmo arquivo em hml e prod
- **WHEN** o stack `atlas-hml` usa `IMAGE_TAG=hml` e o `atlas-prod` usa `IMAGE_TAG=1.0`
- **THEN** ambos sobem do mesmo arquivo, cada um com a sua rede, seus volumes e seus hosts

#### Scenario: Tag não informada
- **WHEN** o stack é criado sem a variável de tag
- **THEN** o Portainer recusa o stack com a mensagem de variável obrigatória

### Requirement: Ordem de subida sem depends_on
Como o Swarm ignora `depends_on`, a ordem SHALL vir de repetição e de espera: o `airflow-init` roda uma vez (migração do banco e usuário administrador) e os demais componentes do Airflow SHALL esperar a migração terminar antes de iniciar. O `backend` SHALL só ser considerado saudável quando responder ao health check, e o `frontend` SHALL tolerar o backend indisponível na subida.

#### Scenario: Primeiro boot
- **WHEN** o stack sobe com o volume do Postgres vazio
- **THEN** o Postgres cria os bancos, o `airflow-init` migra o banco e o admin, e `scheduler`, `dag-processor`, `triggerer` e `api-server` ficam saudáveis sem intervenção

#### Scenario: Reinício
- **WHEN** um serviço do Airflow é recriado pelo webhook
- **THEN** ele sobe sem rodar a inicialização de novo e fica saudável

### Requirement: Credenciais por secrets e variáveis
O stack SHALL receber senhas e tokens por variáveis de stack e as chaves das service accounts por Docker secrets montados em `/run/secrets/`, apontados por `GOOGLE_APPLICATION_CREDENTIALS` e `DBT_BQ_KEYFILE`. Nenhum valor de credencial SHALL aparecer no arquivo do stack. As senhas do Postgres do MLflow e do Airflow SHALL ser distintas entre si e da do superusuário.

#### Scenario: Chave do backend
- **WHEN** o backend sobe com o secret de leitura montado
- **THEN** lê o BigQuery e serve o PNG de uma figura do bucket sem receber a chave por variável de ambiente

### Requirement: Artefatos separados por ambiente
O MLflow SHALL gravar os artefatos em `gs://<bucket>/mlflow/<ambiente>` com o ambiente `hml` ou `prod`, e o cache do Cosmos e a documentação do dbt SHALL usar o mesmo ambiente no caminho. hml e prod SHALL nunca escrever no mesmo prefixo.

#### Scenario: hml e prod
- **WHEN** os dois stacks rodam na mesma VPS e no mesmo bucket
- **THEN** cada um grava só em `.../hml/` ou `.../prod/`

### Requirement: Publicação no Traefik
O site e a API SHALL ser publicados pelo Traefik na rede pública com TLS, em hosts definidos por variável. As interfaces do Airflow e do MLflow SHALL ser publicadas só atrás da autenticação própria de cada uma (FAB e basic-auth) e de uma lista de origens permitidas definida por variável. Postgres e Redis SHALL ficar só na rede interna.

#### Scenario: Banco
- **WHEN** alguém tenta acessar a porta do Postgres de fora da VPS
- **THEN** não há porta publicada e a conexão não é possível

### Requirement: Webhook com várias URLs
O secret de webhook de uma imagem SHALL aceitar uma URL por linha, e o job de deploy SHALL chamar todas, falhando se qualquer uma falhar. Isso SHALL cobrir os quatro serviços que usam a imagem do Airflow.

#### Scenario: Imagem do Airflow
- **WHEN** a imagem `airflow:hml` é publicada
- **THEN** os webhooks de `airflow-api-server`, `scheduler`, `dag-processor` e `triggerer` são chamados

### Requirement: Validação antes da VPS
Antes de levar o stack à VPS, ele SHALL ser validado por `docker stack config` e por uma subida real em um Swarm local de um nó, com as páginas `/` e `/previsao`, a API e o MLflow respondendo.

#### Scenario: Stack local
- **WHEN** o stack é implantado localmente com as imagens de teste
- **THEN** todos os serviços chegam ao estado saudável e o site responde HTTP 200
