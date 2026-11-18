# Spec Delta

## Purpose

Dizer, sem vazar nada, quais variáveis cada ambiente precisa e onde cada uma é preenchida.

## ADDED Requirements

### Requirement: Exemplo de dev completo
`platform/.env.example` SHALL listar todas as variáveis lidas pelo `compose.dev.yml` e por `platform/dev.ps1`, cada uma com comentário (para quê, obrigatória ou opcional, padrão), com valores só de exemplo.

#### Scenario: Clone novo
- **WHEN** alguém copia `platform/.env.example` para `platform/.env` e troca apenas as senhas marcadas
- **THEN** `dev.ps1 up` sobe a plataforma sem erro de variável ausente

### Requirement: Exemplo de hml
`deploy/hml.env.example` SHALL listar todas as variáveis do `atlas.stack.yml`, agrupadas em obrigatórias, com padrão e segredos, indicando para cada segredo se vai em variável de stack ou em Docker secret, com valores só de exemplo ou vazios.

#### Scenario: Stack de hml
- **WHEN** alguém cria o stack `atlas-hml` preenchendo as variáveis do exemplo
- **THEN** o Portainer não acusa variável obrigatória ausente

### Requirement: Exemplos em dia e sem credencial
Toda variável referenciada nos arquivos de stack e de compose SHALL existir no exemplo do ambiente correspondente, e o CI SHALL falhar se faltar. Os exemplos SHALL conter apenas valores de exemplo reconhecíveis (`troque-esta-senha`, vazio ou padrões públicos), nunca credenciais reais.

#### Scenario: Variável nova sem exemplo
- **WHEN** um commit adiciona `${NOVA_VARIAVEL}` ao stack sem listá-la em `hml.env.example`
- **THEN** o job de verificação falha apontando o nome

#### Scenario: Valor real no exemplo
- **WHEN** um commit coloca uma senha real em um `.env.example`
- **THEN** o job `secrets` falha
