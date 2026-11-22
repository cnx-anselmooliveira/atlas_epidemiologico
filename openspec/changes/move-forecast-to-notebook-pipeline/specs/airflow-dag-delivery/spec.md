# Spec Delta

## Purpose

Entregar as DAGs e o notebook de previsão ao Airflow a partir do repositório no GitHub, por branch e ambiente, de modo que o merge reflita no Airflow sem reconstruir a imagem.

## ADDED Requirements

### Requirement: DAGs lidas do repositório por ambiente
Em hml e prod, o Airflow SHALL ler as DAGs de um clone do repositório do projeto no GitHub: hml da branch `hml` e prod da branch `main`. Um merge na branch do ambiente SHALL ser refletido nas DAGs e no notebook sem novo build nem redeploy da imagem.

#### Scenario: Merge numa DAG em hml
- **WHEN** uma alteração em `airflow/dags` entra na branch `hml`
- **THEN** a versão nova da DAG aparece no Airflow de hml em até o intervalo de sincronização configurado
- **AND** nenhuma imagem é reconstruída nem reimplantada

#### Scenario: Ambientes isolados
- **WHEN** uma alteração entra na branch `hml`
- **THEN** o Airflow de prod continua com as DAGs da branch `main`

### Requirement: Intervalo de sincronização configurável
O intervalo entre sincronizações SHALL ser configurável por variável do stack, com padrão de poucos minutos, e a branch e o repositório SHALL ser configuráveis por ambiente.

#### Scenario: Branch por variável
- **WHEN** o stack de prod é implantado com a branch `main` e o de hml com a `hml`
- **THEN** cada um sincroniza só a própria branch

### Requirement: Falha de sincronização não derruba o Airflow
Se a sincronização falhar (rede, GitHub indisponível, branch inexistente), o Airflow SHALL continuar executando e agendando as DAGs da última versão sincronizada com sucesso, e a falha SHALL ficar visível nos logs do serviço de sincronização.

#### Scenario: GitHub indisponível
- **WHEN** o GitHub fica inacessível por algumas sincronizações
- **THEN** as DAGs da última versão sincronizada continuam carregadas e executando
- **AND** o serviço de sincronização registra a falha em log

#### Scenario: Primeira partida sem clone
- **WHEN** o Airflow sobe e ainda não há clone disponível
- **THEN** os componentes esperam o primeiro clone em vez de subir sem DAGs
- **AND** o stack informa o motivo da espera

### Requirement: Atualização atômica das DAGs
Os componentes do Airflow SHALL ver sempre uma versão completa do repositório, nunca um clone pela metade: a troca de uma versão por outra SHALL ser atômica do ponto de vista de quem lê os arquivos.

#### Scenario: Troca durante a leitura
- **WHEN** uma sincronização acontece enquanto o processador de DAGs lê os arquivos
- **THEN** ele lê integralmente a versão anterior ou integralmente a nova

### Requirement: Mesmo clone para todos os componentes
O scheduler, o processador de DAGs, o triggerer e o servidor da API SHALL ler as DAGs do mesmo clone, e as tarefas SHALL executar o código da DAG e o notebook da mesma versão que o processador de DAGs serializou.

#### Scenario: Tarefa depois de um merge
- **WHEN** um merge acontece com uma execução em andamento
- **THEN** as tarefas daquela execução continuam usando a versão do início da execução ou falham com mensagem clara, sem misturar versões

### Requirement: Projeto dbt lido do clone
O projeto dbt (`airflow/dags/utfpr_dengue`) e as DAGs que o referenciam SHALL funcionar a partir do clone, com o mesmo resultado que tinham lendo a pasta embutida na imagem.

#### Scenario: Modelo dbt alterado
- **WHEN** um modelo dbt é alterado e o merge é sincronizado
- **THEN** a próxima execução da DAG do dbt usa o modelo novo
- **AND** o cache do Cosmos não serve o resultado da versão anterior

### Requirement: Acesso ao repositório sem segredo quando público
Enquanto o repositório for público, o serviço de sincronização SHALL clonar por HTTPS sem credencial. Se o repositório passar a ser privado, a credencial SHALL vir de um secret do stack, nunca da imagem nem do repositório.

#### Scenario: Repositório público
- **WHEN** o stack é implantado com o repositório público
- **THEN** a sincronização funciona sem nenhum secret de acesso ao GitHub

### Requirement: Imagem não precisa reconstruir por DAG ou notebook
A publicação da imagem do Airflow SHALL deixar de ser disparada por alterações que mudem só DAGs ou notebooks. Alterações no pacote `atlas_ml`, nos venvs, no Dockerfile ou na configuração SHALL continuar disparando a publicação.

#### Scenario: Alteração só em DAG
- **WHEN** um merge muda apenas arquivos de `airflow/dags`
- **THEN** o workflow de publicação da imagem do Airflow não roda

#### Scenario: Alteração no pacote de ML
- **WHEN** um merge muda `ml/src`
- **THEN** a imagem do Airflow é reconstruída e publicada

### Requirement: Validação das DAGs continua no CI
O CI SHALL continuar importando todas as DAGs e executando os testes de DAG antes do merge, para que o que chega ao clone já tenha sido validado.

#### Scenario: DAG com erro de importação
- **WHEN** um pull request introduz uma DAG que não importa
- **THEN** o CI falha e o merge não deve ocorrer

### Requirement: Airflow de dev inalterado
O ambiente de dev SHALL continuar lendo as DAGs da pasta do repositório montada no contêiner, ao vivo, sem depender do serviço de sincronização.

#### Scenario: Edição local em dev
- **WHEN** uma DAG é editada no disco em dev
- **THEN** o Airflow de dev a recarrega sem sincronização via GitHub
