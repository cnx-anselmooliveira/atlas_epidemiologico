# Proposal

## Why

Explorar dados e testar os modelos hoje exige rodar notebooks na máquina de cada pessoa. O Jupyter só existe no ambiente de dev (`platform/compose.dev.yml`, em `127.0.0.1`, com a chave de treino e o token padrão `atlas`).

Queremos um Jupyter no hml, em `jupyter-hml.contovisual.com.br`, com as mesmas versões do que o Airflow roda, para testar e explorar. **Ele é um caderno isolado: não se integra com nada do projeto.** Não recebe credencial, rede interna nem dado de nenhum produto. Se a pessoa quiser dados, ela os baixa e sobe à mão, ou informa uma credencial na própria sessão e a apaga em seguida. Com isso o sistema não ganha segurança nova para manter (sem conta de serviço, IAM, secrets nem usuário no MLflow).

## What Changes

- **Serviço `jupyter` no stack de hml**, publicado em `jupyter-hml.contovisual.com.br` pelo Traefik (HTTPS com certificado automático), sem porta no host. O nome do host vem de uma variável do stack.
- **Protegido por senha e TLS, sem lista de IPs** (decisão do usuário). A senha entra como **hash argon2 na variável `JUPYTER_PASSWORD_HASH`** do stack e do `.env.hml`; o servidor não sobe sem ela e não existe token nem senha padrão. O proxy limita as tentativas por origem e o terminal fica desativado.
- **Isolado:** o serviço fica só na rede pública do Traefik, **sem a rede interna** (não alcança MLflow, Airflow, banco nem Redis), **sem Docker secrets** e sem variável de credencial de nenhum serviço. O `check-stack.sh` passa a garantir isso.
- **Imagem:** o alvo `notebook` de `ml/Dockerfile` passa a ser publicado como `atlas-epidemiologia-ml-notebook`, com a mesma tag do Airflow (mesmas versões do `atlas_ml` e das bibliotecas de ML).
- **Notebooks de modelo à mão:** a imagem leva uma cópia de `ml/notebooks`; na primeira subida o volume de trabalho recebe essa cópia. Os notebooks leem um arquivo parquet que a pessoa sobe; as runs do MLflow ficam locais (`mlruns`).
- **DNS:** registro `jupyter-hml.contovisual.com.br` apontando para o IP do `atlas-hml` (`37.27.80.107`), **só DNS, sem proxy do Cloudflare**, para o limite de tentativas ver o IP real. Já criado.
- **Contêiner contido:** sem root, sem capacidades do Linux, sistema de arquivos raiz somente leitura, limites de CPU e memória, desligável por `JUPYTER_REPLICAS=0`.
- **Dev igual ao hml:** o Jupyter de dev perde a chave do Google e o MLflow, e exige `JUPYTER_TOKEN` sem valor padrão.
- **CI:** notebooks versionados sem saídas (já feito).
- Fora de escopo: prod (o serviço existe, mas só o hml tem host); lista de IPs; integração do Jupyter com BigQuery, bucket, MLflow ou `git-sync`; a entrega das DAGs por `git-sync` (change `move-forecast-to-notebook-pipeline`).

## Capabilities

### New Capabilities
- `jupyter-exploration-service`: Jupyter de exploração no hml, em host próprio com senha e TLS, com as mesmas versões do Airflow, isolado de todos os dados e serviços do projeto e com contêiner contido.

### Modified Capabilities
<!-- Nenhuma em openspec/specs/ (ainda não há specs arquivadas). Esta capacidade já aparece, com acesso por lista de IPs, na change `move-forecast-to-notebook-pipeline`, que deve perder o Jupyter depois (ver tasks.md); a versão válida é a desta change. -->

## Impact

- **Stack (`docker-compose.yml`)**: serviço `jupyter` sem secrets, sem `atlas_internal` e sem credenciais; volume de trabalho; rótulos do Traefik (host, TLS, limite de tentativas); `.env.example` com `JUPYTER_HOST`, `JUPYTER_REPLICAS` e `JUPYTER_PASSWORD_HASH` (sem valor).
- **Imagem e CI**: `ml.yml` publica o alvo `notebook`; `release.yml` e a tabela de imagens do `deploy/README.md` listam a nova imagem; `check-stack.sh` confere o serviço isolado; `ci.yml` verifica notebooks sem saídas.
- **Código**: `ml/Dockerfile`, a configuração do servidor Jupyter (hash lido da variável) e o semeador (só a cópia da imagem); `platform/compose.dev.yml`.
- **Fora do repositório**: o registro DNS (feito) e a variável `JUPYTER_PASSWORD_HASH` no Portainer e no `.env.hml`. Nada de GCP, MLflow ou Docker secret.
- **Risco aceito:** sem lista de IPs, a tela de login fica na internet. Quem entrar no Jupyter não alcança nenhum dado nem serviço do Atlas, só o que a pessoa subir para lá; o limite de tentativas, a senha forte com hash argon2 e o serviço desligável limitam o resto.
