# Spec Delta

## Purpose

Implantar e atualizar os componentes na VPS via Portainer, em stacks independentes para aplicação e dados, com configuração e segredos fora das imagens e do repositório.

## ADDED Requirements

### Requirement: Stacks independentes
A aplicação (frontend, backend, cache) e a plataforma de dados (Airflow e dependências) SHALL ser definidas em arquivos compose separados e implantadas como stacks distintas no Portainer.

#### Scenario: Atualizar só a aplicação
- **WHEN** a stack da aplicação é reimplantada
- **THEN** os serviços da stack de dados não são reiniciados

### Requirement: Deploy automático após publicação
Após a publicação bem-sucedida de uma imagem em `main`, o CI SHALL acionar a atualização da stack correspondente no Portainer, que SHALL baixar a nova imagem e recriar o serviço.

#### Scenario: Nova imagem do backend
- **WHEN** o CI publica uma nova imagem do backend
- **THEN** o webhook do Portainer da stack da aplicação é chamado
- **AND** o serviço do backend passa a rodar a imagem recém-publicada

#### Scenario: Webhook falha
- **WHEN** a chamada ao webhook do Portainer retorna erro
- **THEN** o workflow do CI termina com falha visível

### Requirement: Exposição via Traefik
Frontend e API SHALL ser expostos somente pelo Traefik existente na rede `network_public`, com HTTPS, nos domínios `dengue.contovisual.com.br` e `api.dengue.contovisual.com.br`; o cache e serviços internos SHALL NOT ser expostos à internet.

#### Scenario: Acesso ao cache de fora
- **WHEN** alguém tenta conectar na porta do Redis pelo IP público da VPS
- **THEN** a conexão é recusada

### Requirement: Segredos fora do compose
Credenciais (chave GCP, tokens) SHALL ser fornecidas como variáveis de ambiente ou segredos da stack no Portainer, e os arquivos compose versionados SHALL conter apenas referências a elas.

#### Scenario: Revisão do compose versionado
- **WHEN** os arquivos em `deploy/` são inspecionados
- **THEN** não contêm valores de credenciais, apenas referências a variáveis

### Requirement: Rollback por tag
O deploy SHALL permitir voltar um serviço para uma imagem anterior escolhendo uma tag imutável já publicada, sem rebuild.

#### Scenario: Reverter backend
- **WHEN** a stack da aplicação é atualizada com a tag do commit anterior do backend
- **THEN** o backend volta a rodar a imagem daquele commit

### Requirement: Recuperação automática
Os serviços SHALL ser reiniciados automaticamente em caso de falha e o backend SHALL só receber tráfego após passar no health check.

#### Scenario: Backend cai
- **WHEN** o processo do backend termina com erro
- **THEN** o orquestrador sobe uma nova réplica do serviço
