# Spec Delta

## Purpose

Garantir, antes de cada merge em hml e main, que o stack e os arquivos de que ele depende estão presentes e válidos.

## ADDED Requirements

### Requirement: Arquivos do stack presentes
O CI SHALL falhar um PR ou push para `hml` ou `main` se faltar `docker-compose.yml`, `.env.example` ou `platform/postgres/init-databases.sh`, ou se o stack referenciar outro arquivo do repositório que não exista.

#### Scenario: Script do Postgres ausente
- **WHEN** um PR remove `platform/postgres/init-databases.sh`
- **THEN** o job `stack` falha apontando o arquivo e o `docker-compose.yml` que o referencia

### Requirement: Stack válido para hml e prod
O job `stack` SHALL executar `docker stack config` com as variáveis do `.env.example` para hml (`ATLAS_ENV=hml`, `IMAGE_TAG=hml`) e para prod (`ATLAS_ENV=prod`, `IMAGE_TAG=1.0`) e falhar se qualquer uma não validar.

#### Scenario: Variável obrigatória nova
- **WHEN** um PR adiciona `${NOVA:?}` ao stack sem listá-la no `.env.example`
- **THEN** o job falha por variável ausente

### Requirement: Propriedades de segurança do stack
O job `stack` SHALL falhar se o stack resolvido tiver imagem com tag `latest`, porta publicada no host, serviço sem imagem do DockerHub do projeto ou oficial conhecida, ou secret que não seja externo.

#### Scenario: Porta publicada
- **WHEN** um PR publica a porta 5432 do Postgres no host
- **THEN** o job falha dizendo que o stack não pode publicar portas

### Requirement: Job no portão de merge
Os jobs `promocao` e `stack` SHALL fazer parte do `ci-ok`, de modo que um deles falho ou pulado impeça o merge.

#### Scenario: Job pulado
- **WHEN** o job `stack` é pulado
- **THEN** o `ci-ok` falha
