# Spec Delta

## Purpose

Garantir que cada modelo seja rastreável até o código, a imagem e os dados que o produziram, e que só chegue a produção depois de passar por homologação.

## ADDED Requirements

### Requirement: Metadados obrigatórios de reprodutibilidade
Toda run de treino SHALL registrar como tags:
- ambiente (`dev`, `hml`, `prod`);
- commit git;
- tag da imagem;
- identificação da versão dos dados de entrada (ou `synthetic` no experimento de exemplo).

Uma run sem essas tags SHALL falhar antes de treinar.

#### Scenario: Run completa
- **WHEN** o treino de exemplo termina
- **THEN** a run tem as tags `atlas.env`, `atlas.git_sha`, `atlas.image_tag` e `atlas.data_version` preenchidas

#### Scenario: Commit desconhecido
- **WHEN** o treino é iniciado num diretório sem git e sem a variável de commit definida
- **THEN** o treino termina com erro antes de registrar qualquer métrica

### Requirement: Registro de modelos por nome
Modelos treinados para uso SHALL ser registrados no registro de modelos com nome estável (ex.: `atlas-example`), gerando uma nova versão a cada registro.

#### Scenario: Segundo registro
- **WHEN** o mesmo modelo é registrado duas vezes
- **THEN** existem as versões 1 e 2 do mesmo nome

### Requirement: Aliases por ambiente
Cada ambiente SHALL consumir modelos apenas pelo alias correspondente (`@dev`, `@hml`, `@prod`), nunca por número de versão fixo no código.

#### Scenario: Atualizar homologação
- **WHEN** o alias `@hml` é movido da versão 2 para a versão 3
- **THEN** quem carrega `models:/atlas-example@hml` passa a receber a versão 3 sem mudança de código

### Requirement: Promoção em ordem
O alias `@prod` SHALL ser atribuído somente a uma versão que esteja ou tenha estado em `@hml` e cujas métricas de validação tenham sido registradas. Tentativas de promover direto de `@dev` para `@prod` SHALL ser recusadas pela ferramenta de promoção.

#### Scenario: Promoção direta recusada
- **WHEN** alguém tenta promover para `@prod` uma versão que nunca teve `@hml`
- **THEN** a ferramenta de promoção recusa com mensagem explicando a ordem dev → hml → prod
- **AND** o alias `@prod` não muda

#### Scenario: Promoção válida
- **WHEN** a versão 3, que está em `@hml` com métricas de validação, é promovida
- **THEN** `@prod` aponta para a versão 3
- **AND** a versão recebe a tag com data e autor da promoção

### Requirement: Registro de dev não é fonte de produção
Modelos registrados no MLflow de dev local SHALL NOT ser promovidos para hml ou prod. Para chegar a hml, o treino SHALL ser executado contra o MLflow da VPS com a imagem de tag `hml`.

#### Scenario: Modelo treinado no notebook
- **WHEN** um modelo existe apenas no MLflow de dev local
- **THEN** ele não aparece no registro da VPS e não pode receber `@hml`
