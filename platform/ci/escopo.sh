#!/usr/bin/env bash
# Via rápida do CI (mudança add-forecast-model-dags): decide se um conjunto de arquivos alterados
# dispensa o build das imagens, o e2e da plataforma, o frontend, o backend e os testes do pacote ml.
#
# Entrada: um caminho por linha no stdin (saída de `git diff --name-only`).
# Saída: `rapido=true` ou `rapido=false` no stdout (formato do $GITHUB_OUTPUT); no stderr, o motivo.
#
# Rápido só quando TODOS os arquivos são de:
#   airflow/dags/**      (exceto airflow/dags/utfpr_dengue/pyproject.toml e uv.lock: dependências do dbt
#                         entram na imagem do Airflow)
#   ml/notebooks/**      (chegam ao Airflow pelo git-sync, não pela imagem)
#   airflow/tests/**     (montados do commit no job dags da via rápida)
#   openspec/**, docs/**, *.md
# Lista vazia é tratada como completo: sem diff confiável não há como garantir nada.
set -euo pipefail

total=0
while IFS= read -r arquivo || [ -n "$arquivo" ]; do
  arquivo="${arquivo%$'\r'}"
  [ -n "$arquivo" ] || continue
  total=$((total + 1))
  case "$arquivo" in
    airflow/dags/utfpr_dengue/pyproject.toml | airflow/dags/utfpr_dengue/uv.lock)
      echo "escopo: completo (dependência do dbt na imagem: ${arquivo})" >&2
      echo "rapido=false"
      exit 0
      ;;
    airflow/dags/* | airflow/tests/* | ml/notebooks/* | openspec/* | docs/* | *.md) ;;
    *)
      echo "escopo: completo (${arquivo} fora da via rápida)" >&2
      echo "rapido=false"
      exit 0
      ;;
  esac
done

if [ "$total" -eq 0 ]; then
  echo "escopo: completo (nenhum arquivo alterado informado)" >&2
  echo "rapido=false"
  exit 0
fi
echo "escopo: via rápida (${total} arquivo(s), todos em DAGs, notebooks, docs ou OpenSpec)" >&2
echo "rapido=true"
