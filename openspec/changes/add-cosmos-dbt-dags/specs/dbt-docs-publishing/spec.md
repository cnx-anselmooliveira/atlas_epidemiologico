# Spec Delta

## Purpose

Disponibilizar a documentação do projeto dbt (models, colunas, testes e linhagem) dentro do Airflow de cada ambiente, gerada sob demanda a partir do mesmo código que roda a modelagem.

## ADDED Requirements

### Requirement: Geração sob demanda
O Airflow SHALL ter uma DAG sem agendamento que gera a documentação do projeto dbt contra o BigQuery do ambiente e grava `index.html`, `manifest.json` e `catalog.json` no bucket de artefatos, numa pasta por ambiente (`dbt_docs/<ambiente>/`). Uma nova geração SHALL substituir os arquivos anteriores da mesma pasta.

#### Scenario: Disparo manual em dev
- **WHEN** a DAG de documentação é disparada no Airflow de dev
- **THEN** `gs://ppgcc-bucket/dbt_docs/dev/` passa a ter `index.html`, `manifest.json` e `catalog.json` da execução

#### Scenario: Ambientes separados
- **WHEN** a DAG roda em hml
- **THEN** os arquivos vão para `dbt_docs/hml/`, e a pasta de dev não muda

### Requirement: Documentação visível no Airflow
O Airflow SHALL exibir a documentação publicada do seu ambiente num menu próprio, lida diretamente do bucket com a credencial configurada no Airflow, sem copiar arquivos para dentro da imagem.

#### Scenario: Consulta depois da geração
- **WHEN** alguém abre o menu de documentação do dbt no Airflow, depois de uma execução bem-sucedida da DAG de documentação
- **THEN** a página mostra os models do projeto com descrições e linhagem, incluindo `gold_dengue_casos_provaveis_uf_semanal`

#### Scenario: Nada publicado ainda
- **WHEN** o menu é aberto antes da primeira geração
- **THEN** o Airflow informa que a documentação não foi encontrada, sem erro nas demais páginas

### Requirement: Arquivos servidos com o tipo certo
Os arquivos publicados SHALL ter o tipo de conteúdo correspondente (`text/html`, `application/json`), para que o navegador execute a página de documentação.

#### Scenario: Página interativa
- **WHEN** o `index.html` publicado é aberto pelo Airflow
- **THEN** a busca e o grafo de linhagem funcionam

### Requirement: Credenciais fora do código e das imagens
O acesso ao bucket SHALL usar uma Connection do Airflow. Nenhuma chave SHALL ficar no repositório, nas imagens ou nos logs. Em dev, a Connection SHALL apontar para a chave montada em tempo de execução.

#### Scenario: Ambiente da VPS
- **WHEN** a DAG roda em hml ou prod
- **THEN** ela usa a Connection cadastrada pela UI daquele Airflow, sem mudança de código
