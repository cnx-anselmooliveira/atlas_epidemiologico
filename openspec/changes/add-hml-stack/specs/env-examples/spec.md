# Spec Delta

## Purpose

Dizer, sem vazar nada, quais variáveis o projeto precisa, com um único arquivo de exemplo e um `.env` local.

## ADDED Requirements

### Requirement: Um único exemplo
O repositório SHALL ter um único `.env.example`, na raiz, com todas as variáveis lidas pelo `platform/compose.dev.yml`, pelo `deploy/atlas.stack.yml`, pelo backend e pelo site. Cada variável SHALL ter comentário (para quê, obrigatória ou opcional, padrão, se é segredo) e os grupos SHALL separar o que vale só em desenvolvimento local do que vale no stack de hml e prod. Não SHALL existir outro arquivo `*.env.example` no repositório.

#### Scenario: Clone novo
- **WHEN** alguém copia `.env.example` para `.env` e troca apenas as senhas marcadas
- **THEN** `platform/dev.ps1 up` sobe a plataforma sem erro de variável ausente

#### Scenario: Stack no Portainer
- **WHEN** alguém cria o stack `atlas-hml` carregando as variáveis do `.env.example` e preenchendo os segredos
- **THEN** o Portainer não acusa variável obrigatória ausente

### Requirement: `.env` local fora do Git
O `.env` local SHALL ser ignorado pelo Git e pelo `.dockerignore`, e os scripts de desenvolvimento (`dev.ps1`, `e2e.sh` quando aplicável e os scripts do site) SHALL ler o `.env` da raiz. Senhas e tokens reais SHALL existir só no `.env` local e nas variáveis do stack no Portainer.

#### Scenario: Commit acidental
- **WHEN** `.env` é adicionado ao índice
- **THEN** o hook e o job `secrets` barram o commit

### Requirement: Exemplo em dia e sem credencial
Toda variável referenciada nos arquivos de compose e de stack SHALL existir no `.env.example`, e o CI SHALL falhar se faltar. O exemplo SHALL conter apenas valores reconhecíveis como exemplo (`troque-esta-senha`, vazio ou padrões públicos), nunca credenciais reais.

#### Scenario: Variável nova sem exemplo
- **WHEN** um commit adiciona `${NOVA_VARIAVEL}` ao stack sem listá-la em `.env.example`
- **THEN** o job de verificação falha apontando o nome

#### Scenario: Valor real no exemplo
- **WHEN** um commit coloca uma senha real no `.env.example`
- **THEN** o job `secrets` falha
