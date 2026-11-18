# Spec Delta

## Purpose

Manter os microdados de dengue do SINAN atualizados no BigQuery a partir do OpenDataSUS, sem intervenção manual. O landing do bucket é um espelho dos arquivos de origem e alimenta a tabela bronze e a modelagem existente.

## ADDED Requirements

### Requirement: Sync diário com a origem
Uma vez por dia, o sistema SHALL comparar os arquivos anuais de dengue do SINAN no OpenDataSUS (de 2000 até o ano corrente) com o landing do bucket, sem baixar os arquivos. A comparação SHALL usar o ETag e a data de modificação da origem guardados junto de cada arquivo do landing. Quando não houver diferença, a execução SHALL terminar sem efeito.

#### Scenario: Comparação sem download
- **WHEN** a verificação do dia roda
- **THEN** a origem é consultada só pelos cabeçalhos dos arquivos, e o landing pela listagem dos objetos com sua metadata

### Requirement: Plano de sync
A comparação SHALL produzir um plano com:
- os arquivos a baixar: novos na origem, ou com ETag ou data de modificação diferentes;
- os arquivos a apagar: presentes no landing e ausentes na origem;
- os anos a carregar na bronze.

#### Scenario: Arquivo do ano corrente atualizado
- **WHEN** a origem publica uma nova versão de `DENGBR26.csv.zip` e os outros anos não mudam
- **THEN** o plano tem só 2026 para baixar e carregar

#### Scenario: Nada mudou
- **WHEN** a verificação do dia não encontra diferença até o fim da janela de espera
- **THEN** o sync termina sem efeito no bucket e na bronze

#### Scenario: Bucket vazio
- **WHEN** o landing não tem nenhum arquivo
- **THEN** todos os anos disponíveis na origem entram no plano para baixar e carregar

### Requirement: Landing como espelho exato
O landing SHALL conter exatamente os arquivos presentes na origem, cada um na versão atual.
- Um arquivo alterado na origem SHALL substituir o anterior no landing.
- Um arquivo que deixou de existir na origem SHALL ser apagado do landing, junto com a versão descompactada.

Cada arquivo do landing SHALL guardar o ETag e a data de modificação da origem que o geraram.

#### Scenario: Versão nova substitui a antiga
- **WHEN** `DENGBR26.csv.zip` muda na origem
- **THEN** o landing passa a ter só a versão nova desse arquivo, com o ETag novo registrado

#### Scenario: Arquivo removido da origem
- **WHEN** um arquivo anual some da origem
- **THEN** ele é apagado do landing, os dados daquele ano saem da tabela bronze e a modelagem roda na mesma execução

### Requirement: Tabela bronze materializada por ano
Os dados de cada ano SHALL ser carregados do landing numa tabela bronze no BigQuery com:
- todas as colunas do arquivo de origem, como texto;
- o ano, a versão (ETag), o caminho do arquivo e o momento da carga.

A carga de um ano SHALL substituir integralmente os dados daquele ano, sem duplicar, e SHALL NOT alterar os demais anos. Uma carga que falhe no meio SHALL NOT deixar o ano pela metade.

#### Scenario: Recarga do mesmo ano
- **WHEN** o ano de 2026 é carregado com uma versão nova
- **THEN** a bronze tem só as linhas da versão nova para 2026, e os outros anos continuam iguais

#### Scenario: Coluna nova na origem
- **WHEN** o arquivo de um ano traz uma coluna que os anteriores não tinham
- **THEN** a carga acrescenta a coluna (nula nos outros anos) em vez de falhar

### Requirement: Validação antes de marcar como carregado
Antes de marcar a versão de um ano como carregada na bronze, o sistema SHALL conferir se o número de linhas da partição é igual ao número de registros do arquivo e se as colunas obrigatórias existem. Divergência SHALL falhar a execução sem marcar o ano, e a verificação do dia seguinte SHALL tentar carregar de novo.

#### Scenario: Carga incompleta
- **WHEN** a partição carregada tem menos linhas que o arquivo, ou não há coluna de classificação final (nem `CLASSI_FIN` nem `CON_CLASSI`)
- **THEN** a validação falha, o ano não é marcado como carregado e entra de novo no plano do dia seguinte

#### Scenario: Landing atualizado, bronze não
- **WHEN** o arquivo foi baixado para o landing, mas a carga na bronze falhou
- **THEN** a próxima verificação detecta que a bronze está atrás do landing e carrega o ano sem baixar de novo

### Requirement: Colunas obrigatórias
As colunas obrigatórias SHALL ser as usadas pela modelagem: data de notificação, UF e município de notificação e de residência, data de início dos sintomas, classificação final e evolução. Os nomes do layout antigo do SINAN (2000–2006) SHALL valer como alternativa.

#### Scenario: Layout antigo
- **WHEN** o arquivo de 2000 traz `CON_CLASSI` e `CON_EVOLUC` em vez de `CLASSI_FIN` e `EVOLUCAO`
- **THEN** a validação aceita o ano

### Requirement: Sync e modelagem na mesma execução diária
A DAG da ETL SHALL rodar uma vez por dia e também SHALL aceitar disparo manual. Em cada execução, o sync do SINAN SHALL rodar antes da modelagem dbt. A modelagem SHALL rodar só quando algum ano tiver sido carregado na bronze ou removido dela, ou quando o disparo pedir para forçar a modelagem. Do contrário, a modelagem SHALL ser pulada, sem custo de BigQuery.

#### Scenario: Dia com dados novos
- **WHEN** a execução diária carrega uma versão nova de 2026 na bronze
- **THEN** os grupos do dbt (seed, bronze, silver e gold) rodam na mesma execução, depois do sync

#### Scenario: Dia sem novidade
- **WHEN** a verificação do dia não encontra diferença entre a origem e o landing
- **THEN** a execução termina sem gravar no bucket, sem mexer na bronze e com os grupos do dbt pulados

#### Scenario: Forçar a modelagem
- **WHEN** alguém dispara a DAG manualmente pedindo para forçar a modelagem, e não há dados novos na origem
- **THEN** a origem é verificada uma vez, sem espera, e o dbt roda

### Requirement: Contrato da modelagem preservado
O model bronze de casos do Brasil SHALL ler a tabela bronze do OpenDataSUS, nos dois layouts do SINAN (2000–2006 e 2007 em diante), e entregar as mesmas colunas e semânticas de antes:
- UF como sigla;
- município com o código de 7 dígitos do IBGE;
- datas como `DATE`;
- classificação final com o código original.

As camadas silver e gold SHALL continuar funcionando sem mudança de contrato. A fonte anterior (Base dos Dados) SHALL continuar selecionável por configuração.

#### Scenario: Equivalência nos anos fechados
- **WHEN** a modelagem roda com a fonte OpenDataSUS
- **THEN** em cada ano até 2020, exceto 2014 e 2015, o total de notificações por UF é idêntico ao da fonte Base dos Dados

#### Scenario: Exceção conhecida de 2014 e 2015
- **WHEN** a modelagem roda com a fonte OpenDataSUS
- **THEN** os anos de 2014 e 2015 vêm sem os casos descartados e sem os confirmados do esquema antigo de classificação, e a diferença nos casos prováveis (8,4% e 4,5% abaixo da Base dos Dados) fica registrada na documentação como limitação aceita

#### Scenario: Anos recentes republicados
- **WHEN** a modelagem roda com a fonte OpenDataSUS
- **THEN** em cada ano encerrado a partir de 2021, o total por UF é maior ou igual a 90% do da fonte Base dos Dados (a fonte nova ganha notificações e reclassifica casos), e as UFs abaixo disso ficam registradas na documentação

#### Scenario: Ano corrente
- **WHEN** a comparação inclui o ano corrente, ainda em investigação
- **THEN** ele fica fora do critério e só é documentado, porque as notificações ainda mudam de classe entre as publicações

#### Scenario: Rollback
- **WHEN** a variável de fonte é definida como `basedosdados`
- **THEN** a modelagem volta a usar a tabela anterior, sem mudança de código

### Requirement: Credenciais e custo controlados
O sync SHALL usar a Connection do Airflow para o bucket e o BigQuery, sem chave em código ou imagem. A verificação diária SHALL NOT baixar arquivos nem consultar o BigQuery: só requisições de cabeçalho à origem e a listagem de objetos do bucket.

#### Scenario: Verificação diária sem mudança
- **WHEN** o sensor roda e nada mudou
- **THEN** foram feitas só requisições de cabeçalho (HEAD) à origem e uma listagem do landing, sem download e sem consulta ao BigQuery
