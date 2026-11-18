# Spec Delta

## Purpose

Fazer do README principal uma porta de entrada fiel ao repositório, curta e verificável.

## ADDED Requirements

### Requirement: Três públicos
O `README.md` SHALL ter uma seção para quem quer entender o projeto, uma para quem vai rodá-lo localmente e uma para quem vai implantá-lo, nessa ordem, e SHALL dizer logo no início, em poucas linhas, o que o Atlas é e o que o site mostra.

#### Scenario: Pessoa nova
- **WHEN** alguém abre o README sem conhecer o projeto
- **THEN** em uma tela entende o objetivo, as seções do site e para onde ir para rodar ou implantar

### Requirement: Rodar localmente do zero
A seção de execução local SHALL listar os pré-requisitos, o passo `.env.example` → `.env`, o comando de subida, as portas de todos os serviços (MLflow, Airflow, API, site e Jupyter opcional) e como rodar os testes de cada parte, e todos os comandos SHALL funcionar como escritos.

#### Scenario: Seguindo os passos
- **WHEN** alguém com os pré-requisitos segue a seção em um clone novo
- **THEN** a plataforma sobe, as portas indicadas respondem e os comandos de teste listados executam

### Requirement: Implantação e promoção
A seção de implantação SHALL resumir as imagens publicadas no DockerHub, o fluxo `dev` → `hml` → `main` com as tags (`dev`, `hml`, `X.Y`), o stack único `docker-compose.yml` da raiz para hml e prod no Portainer e onde entra cada tipo de credencial, e SHALL apontar para `deploy/README.md` e `platform/README.md` em vez de repetir o passo a passo.

#### Scenario: Quem implanta
- **WHEN** alguém precisa criar o stack de hml
- **THEN** o README diz qual arquivo e qual branch usar e leva ao passo a passo em `deploy/README.md`

### Requirement: Resumir e apontar
O README SHALL resumir cada parte do repositório e apontar para o README da pasta, sem repetir procedimentos que já existem neles, e SHALL listar todas as pastas de primeiro nível relevantes (`ml`, `airflow`, `backend`, `frontend`, `infra/mlflow`, `platform`, `deploy`, `docs`, `openspec`).

#### Scenario: Pasta nova
- **WHEN** uma pasta de primeiro nível relevante é adicionada sem constar no README
- **THEN** a verificação automática falha apontando a pasta

### Requirement: Segurança resumida
O README SHALL ter uma seção curta com o princípio de que nenhuma credencial vai para o Git e dizer onde cada tipo de segredo entra, com link para a política de segurança e para `deploy/README.md`.

#### Scenario: Pergunta sobre credenciais
- **WHEN** alguém procura onde colocar uma senha ou chave
- **THEN** a seção de segurança indica o `.env` local ou o Portainer, as Connections do Airflow ou os secrets do GitHub, conforme o caso

### Requirement: Sem referências obsoletas
O README SHALL NOT citar a DAG `atlas_ml_example_training`, `platform/.env`, `deploy/app.stack.yml`, os exemplos de variáveis antigos, a Base dos Dados como fonte do SINAN, nem descrever o site ou o `deploy/` como "em reconstrução" ou "em construção". A verificação automática SHALL falhar se algum voltar.

#### Scenario: Termo obsoleto
- **WHEN** um commit reintroduz `platform/.env` no README
- **THEN** o job `lint` falha apontando a linha

### Requirement: Links e idioma
Todo link relativo do README SHALL apontar para um arquivo ou pasta existente, e o texto SHALL estar em português do Brasil, com os nomes de comando, arquivo e variável em formato de código.

#### Scenario: Link quebrado
- **WHEN** um arquivo apontado pelo README é movido sem atualizar o link
- **THEN** a verificação automática falha apontando o link
