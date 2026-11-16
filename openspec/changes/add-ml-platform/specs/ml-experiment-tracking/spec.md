# Spec Delta

## Purpose

Oferecer um servidor de rastreamento de experimentos de ML em que parâmetros, métricas, artefatos e modelos sobrevivem a reinícios e ficam acessíveis à equipe, local e na VPS.

## ADDED Requirements

### Requirement: Metadados persistentes
O servidor de rastreamento SHALL guardar experimentos, runs, métricas e registro de modelos num banco relacional persistente, de modo que reiniciar ou recriar o container não perca dados.

#### Scenario: Recriar o container do servidor
- **WHEN** o container do MLflow é removido e criado de novo
- **THEN** os experimentos e runs registrados antes continuam listados com as mesmas métricas

### Requirement: Artefatos no armazenamento de objetos via servidor
Na VPS, os artefatos SHALL ser gravados no bucket GCS configurado, sob o prefixo `mlflow/vps`. No dev local, SHALL ir para um volume Docker persistente por padrão, ou para o GCS sob `mlflow/dev` quando um bucket for configurado. Clientes SHALL enviar e baixar artefatos pelo próprio servidor, sem credencial do armazenamento.

#### Scenario: Cliente sem credencial do GCS
- **WHEN** um treino sem nenhuma credencial do GCS registra um arquivo como artefato no MLflow da VPS
- **THEN** o upload termina com sucesso
- **AND** o arquivo aparece no bucket sob `mlflow/vps`

#### Scenario: Dev sem bucket configurado
- **WHEN** o compose de dev sobe sem `MLFLOW_ARTIFACTS_BUCKET` no `.env`
- **THEN** o MLflow aceita artefatos e os guarda num volume local que sobrevive ao reinício da stack

### Requirement: Autenticação na VPS
O servidor na VPS SHALL exigir autenticação para leitura e escrita e SHALL ser acessível apenas por HTTPS. O servidor de dev local SHALL escutar apenas em `127.0.0.1`.

#### Scenario: Acesso anônimo na VPS
- **WHEN** uma requisição sem credenciais chega ao MLflow da VPS
- **THEN** a resposta é HTTP 401

#### Scenario: Dev local fora da máquina
- **WHEN** outra máquina da rede tenta acessar a porta do MLflow de dev
- **THEN** a conexão é recusada

### Requirement: Health check
O servidor SHALL expor um endpoint de saúde que responde HTTP 200 quando ele está apto a atender requisições, usado pelo orquestrador de containers para reiniciá-lo em caso de falha.

#### Scenario: Banco de metadados indisponível
- **WHEN** o Postgres está fora do ar
- **THEN** o servidor não é considerado saudável e o orquestrador tenta reiniciá-lo

### Requirement: Backup dos metadados
Os metadados da VPS SHALL ter backup diário com retenção mínima de 14 dias, fora do disco do Postgres.

#### Scenario: Restauração
- **WHEN** o banco de metadados é restaurado a partir do último backup
- **THEN** os experimentos e versões de modelos registrados até o backup voltam a ser listados e seus artefatos continuam acessíveis
