#!/usr/bin/env bash
# Barra credenciais no repositório: arquivos que nunca devem ser versionados (chaves, .env,
# pastas secrets/) e conteúdo com cara de segredo (chave privada, service account do Google,
# tokens). Sem rede e sem dependências; não imprime o conteúdo achado, só arquivo:linha.
#
#   platform/ci/check-secrets.sh --staged   # o que está no índice (hook de pre-commit)
#   platform/ci/check-secrets.sh --all      # todos os arquivos rastreados (CI)
#
# Segredos de verdade entram só por fora do Git: variáveis da stack no Portainer, Connections
# e Variables do Airflow, secrets do GitHub (ver deploy/README.md).
set -euo pipefail

modo="${1:---all}"
case "$modo" in
  --staged) cached=(--cached); lista=(git diff --cached --name-only --diff-filter=ACMR) ;;
  --all) cached=(); lista=(git ls-files) ;;
  *) echo "uso: $0 [--staged|--all]" >&2; exit 2 ;;
esac

falhou=0

# 1) nomes de arquivo proibidos (exemplos .env.example são permitidos)
nomes='(^|/)\.env(\.[^/]+)?$|(^|/)secrets/|\.(pem|key|p12|pfx|jks)$|-sa\.json$|service[-_]?account[^/]*\.json$|ppgcc-dengue-project[^/]*\.json$|client_secret[^/]*\.json$|(^|/)credentials?[^/]*\.json$|(^|/)id_(rsa|ed25519|ecdsa)$'
while IFS= read -r arq; do
  [[ "$arq" =~ \.env\.example$ ]] && continue
  if [[ "$arq" =~ $nomes ]]; then
    echo "::error file=${arq}::arquivo de credencial não pode ser versionado: ${arq}"
    falhou=1
  fi
done < <("${lista[@]}")

# 2) conteúdo com cara de segredo
padroes=(
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
  '"private_key"[[:space:]]*:'
  '"type"[[:space:]]*:[[:space:]]*"service_account"'
  'AKIA[0-9A-Z]{16}'
  'gh[pousr]_[A-Za-z0-9]{36,}'
  'github_pat_[A-Za-z0-9_]{50,}'
  'dckr_pat_[A-Za-z0-9_-]{20,}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  '/api/webhooks/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
  'AIza[0-9A-Za-z_-]{35}'
)
for p in "${padroes[@]}"; do
  # -I ignora binários; só informa arquivo:linha (nunca o trecho achado)
  if achados="$(git grep "${cached[@]}" -InE -e "$p" -- . ':!platform/ci/check-secrets.sh' ':!*package-lock.json' ':!*.lock' | cut -d: -f1,2)"; [ -n "$achados" ]; then
    while IFS= read -r loc; do
      echo "::error file=${loc%%:*},line=${loc##*:}::conteúdo com formato de credencial (${p%%[*})"
    done <<< "$achados"
    falhou=1
  fi
done

# 3) stacks em deploy/: campo de credencial só recebe referência (${VAR}, /run/secrets/...) ou fica vazio
cred='^[[:space:]]*-?[[:space:]]*[A-Za-z0-9_]*(PASSWORD|TOKEN|SECRET|KEY|WEBHOOK)[A-Za-z0-9_]*:[[:space:]]*[^[:space:]#]'
ok='(:[[:space:]]*"?(\$\{|/run/secrets/)|:[[:space:]]*""[[:space:]]*$)'
if achados="$(git grep "${cached[@]}" -nE -e "$cred" -- 'docker-compose.yml' 'deploy/*.yml' 'deploy/*.yaml' 2>/dev/null | grep -vE "$ok" | cut -d: -f1,2)"; [ -n "$achados" ]; then
  while IFS= read -r loc; do
    echo "::error file=${loc%%:*},line=${loc##*:}::valor literal em campo de credencial do stack ou de deploy/ (use \${VARIAVEL} ou /run/secrets/...)"
  done <<< "$achados"
  falhou=1
fi

# 4) .env.example: um só, em dia com compose e stack, e só com valores de exemplo
if [ "$modo" = "--all" ]; then
  while IFS= read -r extra; do
    echo "::error file=${extra}::só existe um exemplo de variáveis: o .env.example da raiz (${extra} deve ser removido)"
    falhou=1
  done < <(git ls-files | grep -E '(^|/)\.env\.example$|\.env\.example$' | grep -vx '\.env\.example' || true)
  if [ ! -f .env.example ]; then
    echo "::error::falta o .env.example da raiz"
    falhou=1
  else
    # toda ${VARIAVEL} de compose e stack precisa estar no exemplo (ATLAS_GIT_SHA vem do script; HOSTNAME é do container)
    for arq in platform/compose.dev.yml platform/compose.ca.yml docker-compose.yml; do
      [ -f "$arq" ] || continue
      while IFS= read -r nome; do
        case "$nome" in ATLAS_GIT_SHA|HOSTNAME) continue ;; esac
        if ! grep -qE "^${nome}=" .env.example; then
          echo "::error file=${arq}::variável ${nome} não está no .env.example"
          falhou=1
        fi
      done < <(grep -oE '\$\{[A-Z_][A-Z0-9_]*' "$arq" | sed 's/^\${//' | sort -u)
    done
    # campos de credencial do exemplo: vazios ou valores de exemplo reconhecíveis
    while IFS=: read -r num linha; do
      valor="${linha#*=}"
      case "$valor" in ""|troque-esta-senha|atlas) ;; *)
        echo "::error file=.env.example,line=${num}::valor real em campo de credencial do exemplo (use troque-esta-senha ou deixe vazio)"
        falhou=1 ;;
      esac
    done < <(grep -nE '^[A-Z0-9_]*(PASSWORD|TOKEN|SECRET|KEY)[A-Z0-9_]*=' .env.example)
  fi
fi

if [ "$falhou" -ne 0 ]; then
  echo "Credenciais não vão para o Git. Use variáveis da stack no Portainer, Connections/Variables do Airflow ou secrets do GitHub (deploy/README.md)." >&2
  exit 1
fi
echo "check-secrets (${modo}): nenhuma credencial encontrada"
