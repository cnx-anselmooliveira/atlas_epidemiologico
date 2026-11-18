# Spec Delta

## Purpose

Levar o stack e as imagens de `dev` até hml e produção de forma controlada, sem divergência de definição entre as branches de implantação.

## ADDED Requirements

### Requirement: Produção é a main
O ambiente de produção SHALL ser servido pela branch `main`, sem branch `prod` separada. O stack `atlas-hml` SHALL ler a branch `hml` e o `atlas-prod` SHALL ler a `main`.

#### Scenario: Branch de produção
- **WHEN** o stack `atlas-prod` é criado no Portainer
- **THEN** a referência é `refs/heads/main` e o caminho do arquivo é `docker-compose.yml`

### Requirement: Promoção por PR e na ordem
Mudanças SHALL chegar a `hml` somente por PR vindo de `dev` e a `main` somente por PR vindo de `hml`. O CI SHALL falhar um PR com origem diferente, e os merges SHALL usar commit de merge, sem squash.

#### Scenario: PR com origem errada
- **WHEN** um PR de `dev` para `main` é aberto
- **THEN** o job de promoção falha dizendo que `main` só recebe PR de `hml`

#### Scenario: Ancestralidade
- **WHEN** `hml` é promovida para `main`
- **THEN** todo commit de `hml` passa a ser ancestral de `main`

### Requirement: Branches de implantação protegidas
`hml` e `main` SHALL exigir PR e o check `ci-ok`, bloquear push direto, force-push e exclusão, e valer também para administradores. O CODEOWNERS SHALL cobrir `docker-compose.yml`, `.env.example`, `platform/postgres/` e `deploy/`.

#### Scenario: Push direto
- **WHEN** alguém tenta dar push direto em `hml`
- **THEN** o GitHub recusa

### Requirement: Produção só roda versão imutável
O stack de produção SHALL usar `IMAGE_TAG` no formato `X.Y` (ou `X.Y.Z`), nunca a tag móvel `hml` nem `dev`. O deploy de produção SHALL ser acionado só por tag em `main`.

#### Scenario: Conferência de produção
- **WHEN** o stack `atlas-prod` está no ar
- **THEN** todos os serviços usam imagens com tag de versão e nenhum usa `hml`

### Requirement: Configuração do Portainer por ambiente
A documentação SHALL descrever, para hml e prod, a URL do repositório, a referência da branch, o caminho `docker-compose.yml`, a sincronização por intervalo desligada e o webhook do stack guardado no Environment correspondente. Credencial de leitura do repositório SHALL ser necessária e guardada no Portainer só se o repositório deixar de ser público.

#### Scenario: Repositório público
- **WHEN** o stack é criado a partir do repositório público
- **THEN** nenhuma credencial do GitHub é configurada no Portainer
