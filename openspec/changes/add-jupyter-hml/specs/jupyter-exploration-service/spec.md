# Spec Delta

## Purpose

Oferecer, no hml, um Jupyter de exploração em host próprio, protegido por senha e TLS, com as mesmas versões do que o Airflow executa, isolado de todos os dados e serviços do projeto: ele não recebe credenciais, secrets nem rede interna, e só trabalha com o que a pessoa subir para ele.

## ADDED Requirements

### Requirement: Host próprio com TLS
O Jupyter SHALL ser servido em `jupyter-hml.contovisual.com.br` pelo proxy do projeto, só por HTTPS com certificado válido e sem publicar porta no host. O nome do host SHALL vir de uma variável do stack, de modo que outro ambiente use outro nome.

#### Scenario: Acesso pelo host
- **WHEN** o DNS aponta para o servidor de hml e o serviço está de pé
- **THEN** `https://jupyter-hml.contovisual.com.br` mostra a tela de login com certificado válido
- **AND** o acesso HTTP simples é redirecionado ou recusado

#### Scenario: Sem porta no host
- **WHEN** se inspeciona o serviço no stack
- **THEN** ele não publica nenhuma porta no host

### Requirement: Registro DNS direto ao servidor
O registro `jupyter-hml.contovisual.com.br` SHALL apontar para o mesmo endereço do `atlas-hml.contovisual.com.br`, só como DNS (sem proxy de terceiros), para que o certificado seja emitido e o limite de tentativas enxergue a origem real.

#### Scenario: DNS correto
- **WHEN** se consulta o DNS do host
- **THEN** ele devolve o mesmo endereço do `atlas-hml.contovisual.com.br`

### Requirement: Acesso por senha
Todo acesso ao Jupyter SHALL exigir senha. A senha SHALL chegar ao serviço apenas como hash (variável `JUPYTER_PASSWORD_HASH`); o servidor SHALL falhar ao subir se a variável faltar, estiver vazia ou não parecer um hash, e SHALL NOT existir token ou senha padrão. A senha em texto SHALL NOT aparecer na imagem, no repositório nem em variável do stack.

#### Scenario: Sem credencial
- **WHEN** alguém abre qualquer página do Jupyter sem fazer login
- **THEN** é levado à tela de login e não vê arquivos nem executa código

#### Scenario: Subir sem o hash
- **WHEN** o serviço é iniciado sem `JUPYTER_PASSWORD_HASH`, ou com um valor que não é um hash
- **THEN** ele não sobe e registra o motivo

#### Scenario: Senha incorreta
- **WHEN** alguém tenta entrar com senha errada
- **THEN** o acesso é negado

### Requirement: Limite de tentativas de login
O proxy SHALL limitar o número de requisições por origem ao Jupyter, de modo que tentativas repetidas de senha sejam freadas, e a recusa SHALL aparecer com o código de limite excedido.

#### Scenario: Força bruta
- **WHEN** uma mesma origem envia dezenas de tentativas de login em poucos segundos
- **THEN** o proxy passa a responder com limite excedido (429)
- **AND** uma pessoa usando o Jupyter normalmente não é afetada

### Requirement: Terminal desativado
O servidor SHALL recusar a abertura de terminais.

#### Scenario: Abrir um terminal
- **WHEN** um usuário autenticado tenta abrir um terminal pelo Jupyter
- **THEN** o servidor recusa

### Requirement: Mesmas versões do Airflow
O Jupyter SHALL usar as mesmas versões do pacote `atlas_ml` e das bibliotecas de ML que o Airflow do ambiente (mesmo `ml/uv.lock` e mesmo commit quando as tags de imagem coincidem).

#### Scenario: Versões iguais
- **WHEN** o Jupyter e o Airflow de hml usam a mesma tag de imagem
- **THEN** a versão do `atlas_ml` e as das bibliotecas de ML são iguais nos dois

### Requirement: Sem integração com os dados e serviços do projeto
O Jupyter SHALL NOT receber Docker secrets, credenciais de nenhum serviço (Google Cloud, MLflow, Airflow, banco, Redis) nem acesso à rede interna do stack. Os dados que ele usa SHALL ser os que a pessoa subir para o volume de trabalho ou os que ela obtiver com uma credencial que informe na própria sessão.

#### Scenario: Serviço sem credenciais
- **WHEN** se inspeciona o serviço no stack
- **THEN** ele não tem secrets, não está na rede interna e não tem variável de credencial de nenhum serviço

#### Scenario: Sem alcance aos serviços internos
- **WHEN** um notebook tenta conectar ao MLflow, ao Airflow, ao banco ou ao Redis do stack
- **THEN** a conexão não é possível

### Requirement: Notebooks do repositório e trabalho em cópia
O Jupyter SHALL trazer os notebooks do repositório numa cópia da imagem e, na primeira subida, SHALL copiá-los para o volume de trabalho do usuário, sem sobrescrever trabalho existente.

#### Scenario: Primeira subida
- **WHEN** o serviço sobe com o volume de trabalho vazio
- **THEN** o volume recebe os notebooks da cópia da imagem

#### Scenario: Volume com trabalho
- **WHEN** o serviço sobe com o volume de trabalho já usado
- **THEN** nada do que está no volume é sobrescrito

### Requirement: Contêiner contido e desligável
O Jupyter SHALL executar sem privilégios de administrador, com todas as capacidades do Linux removidas, sistema de arquivos raiz somente leitura (com áreas temporárias e o volume de trabalho graváveis) e limites de CPU e memória que preservem o Airflow e o MLflow. O número de réplicas SHALL ser controlável por variável do stack.

#### Scenario: Consumo alto
- **WHEN** um notebook usa mais memória que o limite
- **THEN** só o contêiner do Jupyter é reiniciado
- **AND** o scheduler do Airflow não é afetado

#### Scenario: Desligar
- **WHEN** a variável de réplicas do Jupyter é 0
- **THEN** o serviço não executa e os outros serviços continuam como estavam

### Requirement: Notebooks versionados sem dados
Os notebooks versionados em `ml/notebooks` SHALL NOT conter saídas de células, para que resultados com dados não cheguem ao repositório público. O CI SHALL falhar se um notebook tiver saídas.

#### Scenario: Notebook com saída
- **WHEN** um pull request inclui um notebook com saídas de células
- **THEN** o CI falha apontando o arquivo

### Requirement: Jupyter de dev igual ao de hml
O Jupyter do ambiente de desenvolvimento SHALL ficar acessível só em `127.0.0.1`, SHALL NOT receber chave do Google Cloud nem credenciais do MLflow, e SHALL exigir um token informado por quem o sobe, sem valor padrão.

#### Scenario: Subir em dev sem token
- **WHEN** o Jupyter de dev é iniciado sem `JUPYTER_TOKEN`
- **THEN** ele não sobe e informa que o token é obrigatório

#### Scenario: Dev sem credenciais
- **WHEN** se inspeciona o serviço do Jupyter de dev
- **THEN** ele não monta chave de conta de serviço nem recebe usuário ou senha do MLflow
