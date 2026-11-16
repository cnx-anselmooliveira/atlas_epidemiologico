# Spec Delta

## Purpose

Manter os microdados de dengue do SINAN atualizados no BigQuery a partir do OpenDataSUS, sem intervenção manual, preservando os arquivos originais e alimentando a modelagem existente.

## ADDED Requirements

### Requirement: Detecção de novas versões
O sistema SHALL verificar periodicamente, sem baixar os arquivos, se algum arquivo anual de dengue do SINAN no OpenDataSUS (2000 até o ano corrente) mudou desde a última carga, comparando o identificador de versão publicado (ETag) e a data de modificação com os registrados na carga anterior. A ingestão SHALL prosseguir só para os anos que mudaram. Quando nada mudou, a execução SHALL terminar sem carregar nada e sem acionar a modelagem.

#### Scenario: Arquivo do ano corrente atualizado
- **WHEN** o OpenDataSUS publica uma nova versão de `DENGBR26.csv.zip` e as dos outros anos não mudam
- **THEN** só o ano de 2026 é ingerido naquela execução

#### Scenario: Nada novo
- **WHEN** a verificação diária não encontra mudança em nenhum arquivo até o fim da janela de espera
- **THEN** a execução termina como pulada, sem gravar no bucket, sem mexer na tabela bronze e sem disparar a modelagem

#### Scenario: Primeira execução
- **WHEN** a tabela de controle está vazia
- **THEN** todos os anos disponíveis são ingeridos

### Requirement: Arquivos brutos preservados no landing
Cada versão ingerida SHALL ser gravada no bucket sem alteração (o zip original), num caminho que identifica o ano e a versão. Versões anteriores SHALL NOT ser sobrescritas. O conteúdo descompactado SHALL ficar ao lado, para a carga.

#### Scenario: Duas versões do mesmo ano
- **WHEN** o arquivo de 2026 muda duas vezes em dias diferentes
- **THEN** o landing tem as duas versões em pastas distintas, cada uma identificada pelo seu ETag

### Requirement: Tabela bronze materializada por ano
Os dados de cada versão SHALL ser carregados no BigQuery numa tabela bronze com:
- todas as colunas do arquivo de origem, como texto;
- o ano do arquivo, a versão (ETag), o caminho do arquivo no landing e o momento da carga.

A carga de um ano SHALL substituir integralmente os dados daquele ano, sem duplicar, e SHALL NOT alterar os demais anos. Uma carga que falhe no meio SHALL NOT deixar o ano pela metade.

#### Scenario: Recarga do mesmo ano
- **WHEN** o ano de 2026 é carregado de novo com uma versão nova
- **THEN** a tabela bronze tem só as linhas da versão nova para 2026, e os outros anos continuam iguais

#### Scenario: Coluna nova na origem
- **WHEN** o arquivo de um ano traz uma coluna que os anteriores não tinham
- **THEN** a carga acrescenta a coluna (nula nos outros anos) em vez de falhar

### Requirement: Validação antes de liberar
Antes de registrar a versão como carregada, o sistema SHALL conferir:
- se o número de linhas na tabela bronze para aquele ano é igual ao número de registros do arquivo;
- se as colunas usadas pela modelagem existem: data de notificação, UF e município de notificação e de residência, data de início dos sintomas, classificação final e evolução.

Divergência SHALL falhar a execução, sem registrar a versão e sem acionar a modelagem.

#### Scenario: Arquivo truncado
- **WHEN** o arquivo baixado tem menos registros que os carregados ou falta a coluna `CLASSI_FIN`
- **THEN** a tarefa de validação falha, a versão não é registrada e a próxima verificação tenta de novo

### Requirement: Modelagem acionada após carga
Depois de pelo menos um ano carregado e validado, o sistema SHALL disparar a DAG de modelagem (`process_etl_atlas`).

#### Scenario: Carga concluída
- **WHEN** a validação de todos os anos alterados passa
- **THEN** a `process_etl_atlas` é disparada uma vez para aquela ingestão

### Requirement: Contrato da modelagem preservado
O model bronze de casos do Brasil SHALL ler a tabela bronze do OpenDataSUS e entregar as mesmas colunas e semânticas de antes:
- UF como sigla;
- município com o código de 7 dígitos do IBGE;
- datas como `DATE`;
- classificação final com o código original.

As camadas silver e gold SHALL continuar funcionando sem mudança de contrato. A fonte anterior (Base dos Dados) SHALL continuar selecionável por configuração.

#### Scenario: Equivalência com a fonte anterior
- **WHEN** a modelagem roda com a fonte OpenDataSUS
- **THEN** para cada ano completo em ambas as fontes, o total de notificações por UF difere em no máximo 1% da fonte Base dos Dados, e as diferenças ficam registradas na documentação

#### Scenario: Rollback
- **WHEN** a variável de fonte é definida como `basedosdados`
- **THEN** a modelagem volta a usar a tabela anterior, sem mudança de código

### Requirement: Credenciais e custo controlados
A ingestão SHALL usar a Connection do Airflow para o bucket e o BigQuery, sem chave em código ou imagem. A verificação de versões SHALL NOT baixar os arquivos.

#### Scenario: Verificação diária sem mudança
- **WHEN** o sensor roda e nada mudou
- **THEN** só foram feitas requisições de cabeçalho (HEAD), sem download nem consulta paga no BigQuery além da leitura da tabela de controle
