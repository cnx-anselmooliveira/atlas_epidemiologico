# Spec Delta

## Purpose

Oferecer um Jupyter para testar e explorar os dados com uma cópia do que o Airflow executa, com acesso somente de leitura aos dados de produção do ambiente e escrita restrita a áreas de sandbox, sem expor dados brutos nem credenciais do pipeline.

## ADDED Requirements

### Requirement: Serviço de exploração em cada ambiente
O serviço Jupyter SHALL existir em dev, hml e prod, cada um lendo apenas os dados do próprio ambiente. O número de réplicas SHALL ser controlável por variável do stack, de modo que desligá-lo não exija alterar os outros serviços.

#### Scenario: Desligar em um ambiente
- **WHEN** a variável de réplicas do Jupyter é definida como 0 no stack de prod
- **THEN** o serviço não executa em prod
- **AND** Airflow, MLflow, API e site continuam como estavam

### Requirement: Cópia do que o Airflow executa
O Jupyter SHALL usar as mesmas versões do pacote `atlas_ml` e das bibliotecas de ML que o Airflow do ambiente (mesmo `ml/uv.lock` e mesmo commit quando as tags de imagem coincidem), e SHALL ler as DAGs e os notebooks do mesmo clone que o Airflow, somente leitura.

#### Scenario: Mesmas versões
- **WHEN** o Jupyter e o Airflow do ambiente usam a mesma tag de imagem
- **THEN** a versão do `atlas_ml` e a das bibliotecas de ML são iguais nos dois

#### Scenario: Explorar sem alterar o Airflow
- **WHEN** o usuário edita um notebook no Jupyter
- **THEN** a edição fica no volume de trabalho do Jupyter
- **AND** o clone lido pelo Airflow não é alterado

### Requirement: Identidade própria de leitura
O Jupyter SHALL acessar o Google Cloud por uma conta de serviço própria, uma por ambiente, entregue por Docker secret. Ele SHALL NOT usar as contas de treino e do dbt, do backend ou do MLflow, nem receber as credenciais do Airflow (banco, JWT, Fernet) ou o usuário administrador do MLflow.

#### Scenario: Auditoria
- **WHEN** uma consulta ao BigQuery parte do Jupyter
- **THEN** o registro de auditoria a atribui à conta de serviço do Jupyter, distinta das demais

#### Scenario: Revogação isolada
- **WHEN** a chave da conta do Jupyter é revogada
- **THEN** Airflow, backend e MLflow continuam funcionando

### Requirement: Dados permitidos no BigQuery
A conta do Jupyter SHALL ler somente os datasets de gold e de previsões do ambiente e SHALL NOT ler as camadas bronze e silver, que têm dados individuais. Só poderá escrever num dataset sandbox do Jupyter, cujas tabelas expiram sozinhas, e o consumo de consultas SHALL ter limite diário.

#### Scenario: Camada bruta negada
- **WHEN** o Jupyter consulta uma tabela das camadas bronze ou silver
- **THEN** o BigQuery nega o acesso

#### Scenario: Escrita fora do sandbox negada
- **WHEN** o Jupyter tenta gravar numa tabela de gold ou de previsões
- **THEN** o BigQuery nega a escrita

#### Scenario: Escrita no sandbox
- **WHEN** o Jupyter grava uma tabela no dataset sandbox
- **THEN** a gravação funciona e a tabela expira no prazo configurado

### Requirement: Dados permitidos no bucket
A conta do Jupyter SHALL ler somente o prefixo de previsões do ambiente e SHALL escrever somente no prefixo próprio do Jupyter no ambiente. Ela SHALL NOT acessar o SINAN bruto (`landing/`), o cache do Cosmos nem a documentação do dbt.

#### Scenario: SINAN bruto negado
- **WHEN** o Jupyter lista ou lê objetos de `landing/`
- **THEN** o bucket nega o acesso

#### Scenario: Escrita no prefixo próprio
- **WHEN** o Jupyter grava um arquivo no prefixo próprio do ambiente
- **THEN** a gravação funciona e o arquivo não aparece nos prefixos que Airflow e backend leem

### Requirement: MLflow sem poluir o oficial
O Jupyter SHALL acessar o MLflow por usuário próprio, com leitura no experimento oficial de previsão e escrita só num experimento sandbox, e SHALL NOT alterar o registro de modelos. As runs criadas no Jupyter SHALL ir para o experimento sandbox.

#### Scenario: Treino de teste no Jupyter
- **WHEN** o notebook do pipeline é executado no Jupyter com o passo `train`
- **THEN** a run aparece no experimento sandbox
- **AND** o experimento oficial e o registro de modelos não mudam

#### Scenario: Registro negado
- **WHEN** o Jupyter tenta registrar um modelo no registro oficial
- **THEN** o MLflow nega a operação

### Requirement: Acesso ao serviço restrito
O Jupyter SHALL não publicar porta no host e SHALL ser acessível só por TLS, pelo proxy do projeto e a partir dos endereços permitidos para administração. O acesso SHALL exigir token ou senha entregue por Docker secret; sem esse valor o serviço SHALL falhar ao subir, em vez de usar um padrão. O terminal do Jupyter SHALL estar desativado.

#### Scenario: Subir sem token
- **WHEN** o serviço é iniciado sem o secret do token
- **THEN** ele não sobe e registra o motivo

#### Scenario: Endereço não permitido
- **WHEN** uma requisição vem de um endereço fora da lista permitida
- **THEN** o proxy a recusa

#### Scenario: Terminal
- **WHEN** alguém tenta abrir um terminal pelo Jupyter
- **THEN** o servidor recusa

### Requirement: Contêiner contido
O Jupyter SHALL executar sem privilégios de administrador, com todas as capacidades do Linux removidas, sistema de arquivos raiz somente leitura (com áreas temporárias e um volume de trabalho graváveis) e limites de CPU e memória que preservem o Airflow e o MLflow.

#### Scenario: Consumo alto
- **WHEN** um notebook usa mais memória que o limite
- **THEN** só o contêiner do Jupyter é reiniciado
- **AND** o scheduler do Airflow não é afetado

### Requirement: Notebooks versionados sem dados
Os notebooks versionados em `ml/notebooks` SHALL NOT conter saídas de células, para que resultados com dados não cheguem ao repositório público. O CI SHALL falhar se um notebook tiver saídas.

#### Scenario: Notebook com saída
- **WHEN** um pull request inclui um notebook com saídas de células
- **THEN** o CI falha apontando o arquivo
