# Spec Delta

## Purpose

Pousar os dados das fontes oficiais de vigilância de dengue na camada raw do BigQuery, uma fonte por vez, de forma repetível e independente de quem dispara a execução (pessoa via CLI ou Airflow).

## ADDED Requirements

### Requirement: Carga por fonte selecionável
O sistema SHALL permitir executar a carga de uma única fonte, informada por nome (ex.: `brasil`, `colombia`, `peru`, `argentina`, `equador`, `bolivia`, `paho`, `municipios`), sem executar as demais.

#### Scenario: Execução de uma fonte específica
- **WHEN** a ingestão é executada com a fonte `colombia`
- **THEN** somente a tabela raw da Colômbia é carregada no BigQuery
- **AND** as tabelas raw das outras fontes permanecem inalteradas

#### Scenario: Fonte desconhecida
- **WHEN** a ingestão é executada com um nome de fonte que não existe
- **THEN** a execução termina com código de saída diferente de zero e lista as fontes válidas

### Requirement: Carga idempotente na camada raw
Cada carga SHALL substituir integralmente o conteúdo da tabela raw da fonte, de modo que executar a mesma carga duas vezes com os mesmos arquivos produza o mesmo resultado.

#### Scenario: Reexecução da mesma carga
- **WHEN** a carga da fonte `peru` é executada duas vezes seguidas com os mesmos arquivos
- **THEN** a tabela raw do Peru tem o mesmo número de linhas após a segunda execução que após a primeira

### Requirement: Colunas de proveniência
Toda linha carregada na camada raw SHALL trazer o arquivo ou recurso de origem e o instante da carga.

#### Scenario: Linha rastreável até a origem
- **WHEN** uma carga termina com sucesso
- **THEN** cada linha da tabela raw tem preenchidos o identificador do arquivo de origem e o timestamp da carga

### Requirement: Falha explícita quando a entrada não existe
A carga de uma fonte SHALL falhar com código de saída diferente de zero e mensagem indicando o caminho ausente quando os arquivos de entrada esperados não existirem, sem afetar a tabela raw existente.

#### Scenario: Arquivo de entrada ausente
- **WHEN** a carga da fonte `bolivia` é executada e o arquivo consolidado da Bolívia não existe
- **THEN** a execução termina com erro informando o caminho esperado
- **AND** a tabela raw da Bolívia mantém o conteúdo anterior

### Requirement: Credenciais por ambiente
A ingestão SHALL obter credenciais do GCP a partir de variáveis de ambiente ou de arquivo montado em tempo de execução, nunca de arquivo versionado no repositório.

#### Scenario: Execução em container sem chave embutida
- **WHEN** a ingestão roda em container com a credencial fornecida por variável de ambiente
- **THEN** a carga autentica no BigQuery sem que nenhum arquivo de chave exista na imagem
