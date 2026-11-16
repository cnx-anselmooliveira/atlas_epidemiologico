# Como contribuir

Obrigado pelo interesse no Atlas Epidemiológico da Dengue! Este guia mostra como preparar o ambiente, testar e propor mudanças. Ao participar, você concorda com o nosso [código de conduta](CODE_OF_CONDUCT.md).

## Antes de começar

- **Bugs e ideias:** abra uma issue usando os modelos de **bug** ou de **melhoria**.
- **Vulnerabilidades de segurança:** *não* abra issue pública. Siga a [política de segurança](SECURITY.md).
- **Mudanças de comportamento** (nova funcionalidade, mudança de modelo, de dados ou de infraestrutura) são planejadas com [OpenSpec](#mudanças-planejadas-com-openspec) antes do código.

## Preparar o ambiente

Pré-requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/), Git, [uv](https://docs.astral.sh/uv/), Node.js 22 (para o `frontend/`) e PowerShell (para os scripts da plataforma).

```sh
git clone https://github.com/cnx-anselmooliveira/atlas_epidemiologico.git
cd atlas_epidemiologico
git switch dev
```

- **Pacote de ML:** `cd ml && uv sync`. Na rede de empresas com inspeção TLS, use `uv sync --native-tls`.
- **Plataforma local** (Postgres, MLflow, Airflow): `./platform/dev.ps1 up`. Veja [`platform/README.md`](platform/README.md).
- **Site:** `cd frontend && npm ci && npm run dev`.

Nunca versione credenciais. Chaves de service account ficam em `platform/secrets/` e configurações locais em `platform/.env`; os dois são ignorados pelo git.

## Rodar os testes

```sh
cd ml
uv run pytest                          # testes do pacote (sem rede, sem credenciais)
uv run ruff check . && uv run ruff format --check .
```

Para a integridade das DAGs, veja [`airflow/README.md`](airflow/README.md). Rode também o que você alterou: build da imagem, `docker compose config` ou `npm run build`. Os pull requests para `hml` e `main` executam todos os testes no GitHub Actions.

## Fluxo de branches

```
feature/minha-mudanca ──PR──► dev ──PR──► hml ──PR──► main ──tag vX.Y──► release
```

- Crie sua branch a partir de `dev` e abra o pull request para **`dev`**.
- `hml` (homologação) só recebe PR vindo de `dev`. `main` (produção) só recebe PR vindo de `hml`.
- Ninguém faz push direto em `hml` ou `main`. As duas exigem pull request com o check **`ci-ok`** verde.
- Versões são tags `vX.Y` em `main`. Cada versão publica as imagens `X.Y` e uma GitHub Release.

## Commits

Faça **um commit por assunto**: não misture uma correção, uma funcionalidade e uma mudança de documentação no mesmo commit. Use um prefixo no título:

| Prefixo | Uso |
|---|---|
| `feat` | nova funcionalidade |
| `fix` | correção de bug |
| `docs` | documentação, specs e planejamento |
| `test` | testes |
| `ci` | GitHub Actions |
| `build` | dependências, Dockerfiles |
| `chore` | manutenção sem efeito no comportamento |

Exemplo: `feat(models): CatBoost com previsões out-of-fold`. Escreva o título e o corpo em português.

## Mudanças planejadas com OpenSpec

Cada mudança de comportamento tem uma pasta em [`openspec/changes/`](openspec/changes/) com a proposta, as specs, o design e as tarefas. O fluxo é:

1. **Propor:** o planejamento é revisado antes de codar.
2. **Implementar:** seguindo `tasks.md` e marcando as tarefas concluídas.
3. **Arquivar:** depois que a mudança chega a produção.

Valide antes de abrir o PR: `npx @fission-ai/openspec@2.0.0 validate --all --strict`.

## Pull requests

- Preencha o modelo de PR: destino correto, testes rodados, commits por assunto, mudança OpenSpec vinculada e nenhum segredo.
- Aplique uma label (`novidade`, `correção`, `documentação`, `infra`). Ela organiza as notas da próxima release.
- O mantenedor ([@cnx-anselmooliveira](https://github.com/cnx-anselmooliveira)) é revisor automático via `CODEOWNERS`.

## Licença

Ao contribuir, você concorda que sua contribuição será distribuída sob a [licença MIT](LICENSE) do projeto.
