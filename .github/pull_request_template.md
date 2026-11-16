## O que muda

<!-- Resumo em 1–3 frases. Link para a issue, se houver. -->

## Mudança OpenSpec

<!-- Pasta em openspec/changes/ e tarefas implementadas, ou "não se aplica". -->

## Checklist

- [ ] Branch de destino correta: `dev` (trabalho novo), `hml` (só PR vindo de `dev`) ou `main` (só PR vindo de `hml`)
- [ ] Testes rodados localmente (`uv run pytest`, `ruff`, build do que foi alterado)
- [ ] Commits por assunto, com prefixo (`feat`, `fix`, `docs`, `test`, `ci`, `build`, `chore`)
- [ ] Tarefas da mudança OpenSpec marcadas e `openspec validate --all --strict` sem erros (se aplicável)
- [ ] Nenhum segredo (chaves, senhas, `.env`, tokens) no diff
- [ ] Label aplicada (`novidade`, `correção`, `documentação` ou `infra`) para as notas da release
