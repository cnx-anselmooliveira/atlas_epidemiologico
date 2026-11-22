#!/usr/bin/env bash
# Valida o stack de hml e prod (docker-compose.yml da raiz) e os arquivos de que ele depende.
# Roda no CI (job "stack", em todo PR e push para hml e main) e na máquina de quem altera o stack:
#
#   bash platform/ci/check-stack.sh
#
# Confere: (a) o stack, o .env.example e o script do Postgres existem, e todo arquivo do
# repositório que o stack referencia (configs.file) também; (b) `docker stack config` valida com
# as variáveis do .env.example para hml (tag hml) e prod (tag 1.0); (c) na saída resolvida, sem
# tag latest, sem porta publicada no host, secrets externos, só imagens do projeto, postgres,
# redis e o git-sync (tag fixa), e o serviço jupyter isolado e contido (sem secrets, sem rede interna, sem credenciais, cap_drop, read_only, ratelimit), e nenhuma tag móvel (hml, dev) quando a tag é de versão.
# Variável STACK_FILE troca o arquivo (testes); o padrão é docker-compose.yml.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
STACK="${STACK_FILE:-docker-compose.yml}"
falhou=0
erro() { echo "::error file=${STACK}::$*"; falhou=1; }

# Python com PyYAML (python3 no Linux; py/python no Windows)
PY=""
for candidato in python3 python py; do
  if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c "import yaml" >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done
[ -n "$PY" ] || { echo "check-stack: Python 3 com PyYAML não encontrado" >&2; exit 2; }

# (a) arquivos
for arq in "$STACK" .env.example platform/postgres/init-databases.sh; do
  [ -f "$arq" ] || erro "arquivo necessário ausente: ${arq}"
done
[ -f "$STACK" ] || { echo "check-stack: sem ${STACK}, nada mais a validar" >&2; exit 1; }

while IFS= read -r ref; do
  ref="${ref%$''}"
  ref="${ref%$'\r'}" # o Python do Windows imprime \r\n
  [ -z "$ref" ] && continue
  [ -f "$ref" ] || erro "o stack referencia ${ref}, que não existe no repositório"
done < <("$PY" - "$STACK" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for c in (d.get("configs") or {}).values():
    f = (c or {}).get("file")
    if f:
        print(f)
for s in (d.get("secrets") or {}).values():
    f = (s or {}).get("file")
    if f:
        print(f)
PY
)

command -v docker >/dev/null 2>&1 || { echo "check-stack: docker não encontrado" >&2; exit 2; }

# (b) e (c): hml com a tag móvel e prod com uma versão
validar() {
  local ambiente="$1" tag="$2" saida resolvido prefixo
  prefixo="$(. ./.env.example; printf '%s' "${IMAGE_REPO_PREFIX}")"
  if ! saida="$(
    set -a
    # shellcheck disable=SC1091
    . ./.env.example
    set +a
    ATLAS_ENV="$ambiente" IMAGE_TAG="$tag" docker stack config -c "$STACK" 2>&1
  )"; then
    erro "docker stack config falhou para ${ambiente} (tag ${tag}): $(printf '%s' "$saida" | head -3 | tr '
' ' ')"
    return
  fi
  resolvido="$(mktemp)"
  printf '%s
' "$saida" > "$resolvido"
  "$PY" - "$resolvido" "$ambiente" "$tag" "$prefixo" <<'PY' || erro "propriedades do stack inválidas para ${ambiente}"
import sys
import yaml

arquivo, ambiente, tag, prefixo = sys.argv[1:5]
d = yaml.safe_load(open(arquivo, encoding="utf-8"))
erros = []
oficiais = {"postgres:16-alpine", "redis:7-alpine", "registry.k8s.io/git-sync/git-sync:v4.4.0"}
for nome, s in (d.get("services") or {}).items():
    img = s.get("image") or ""
    if not img:
        erros.append(f"serviço {nome} sem imagem")
        continue
    versao = img.rsplit("/", 1)[-1]
    if ":" not in versao or versao.endswith(":latest"):
        erros.append(f"serviço {nome}: imagem {img} sem tag fixa ou com latest")
    if img not in oficiais and not img.startswith(prefixo + "-"):
        erros.append(f"serviço {nome}: imagem {img} fora do prefixo {prefixo}-* e da lista oficial")
    if "build" in s:
        erros.append(f"serviço {nome}: build não é permitido no stack")
    if s.get("ports"):
        erros.append(f"serviço {nome}: publica porta no host")
    if img.startswith(prefixo + "-") and not img.endswith(":" + tag):
        erros.append(f"serviço {nome}: imagem {img} não usa a tag {tag} (tag fixa no arquivo?)")
    if tag[0].isdigit() and img.rsplit(":", 1)[-1] in ("hml", "dev", "latest"):
        erros.append(f"serviço {nome}: prod com tag móvel ({img})")
for nome, sec in (d.get("secrets") or {}).items():
    if not (sec or {}).get("external"):
        erros.append(f"secret {nome} não é externo (valor ou arquivo no repositório)")


# Jupyter de exploração: caderno ISOLADO (sem secrets, sem rede interna, sem credenciais de nenhum serviço) e contido
j = (d.get("services") or {}).get("jupyter")
if j is None:
    erros.append("serviço jupyter ausente")
else:
    segredos = sorted({x["source"] if isinstance(x, dict) else x for x in (j.get("secrets") or [])})
    if segredos:
        erros.append(f"serviço jupyter não pode ter secrets (isolado dos dados do projeto): {', '.join(segredos)}")
    redes = j.get("networks") or []
    redes = sorted(redes if isinstance(redes, list) else redes.keys())
    if "atlas_internal" in redes:
        erros.append("serviço jupyter está na rede interna atlas_internal (alcançaria MLflow, Airflow, banco e Redis)")
    ambiente = j.get("environment") or {}
    nomes = set(ambiente) if isinstance(ambiente, dict) else {str(e).split("=", 1)[0] for e in ambiente}
    credenciais = sorted(
        n for n in nomes if n in ("GOOGLE_APPLICATION_CREDENTIALS", "GCP_PROJECT") or n.startswith("MLFLOW_TRACKING")
    )
    if credenciais:
        erros.append(f"serviço jupyter com variáveis de credencial de outros serviços: {', '.join(credenciais)}")
    if "JUPYTER_PASSWORD_HASH" not in nomes:
        erros.append("serviço jupyter sem JUPYTER_PASSWORD_HASH (a senha, só como hash)")
    if "ALL" not in [str(c).upper() for c in (j.get("cap_drop") or [])]:
        erros.append("serviço jupyter sem cap_drop: [ALL]")
    if not j.get("read_only"):
        erros.append("serviço jupyter sem read_only: true")
    if str(j.get("user", "")).split(":")[0] in ("", "0", "root"):
        erros.append("serviço jupyter roda como root (defina user não-root)")
    if j.get("privileged"):
        erros.append("serviço jupyter privilegiado")
    montagens = [str(v.get("source", "")) if isinstance(v, dict) else str(v) for v in (j.get("volumes") or [])]
    if any("docker.sock" in m for m in montagens):
        erros.append("serviço jupyter monta o socket do Docker")
    if any(m.startswith("airflow_dags") or "airflow" in m for m in montagens):
        erros.append("serviço jupyter monta o volume do Airflow (clone das DAGs)")
    rotulos = (j.get("deploy") or {}).get("labels") or {}
    if isinstance(rotulos, list):
        rotulos = dict(r.split("=", 1) for r in rotulos if "=" in r)
    limitadores = {
        k.split(".")[3] for k in rotulos if k.startswith("traefik.http.middlewares.") and ".ratelimit." in k
    }
    usados = {
        m
        for k, v in rotulos.items()
        if k.startswith("traefik.http.routers.") and k.endswith(".middlewares")
        for m in str(v).split(",")
    }
    if not limitadores & {m.split("@")[0] for m in usados}:
        erros.append("roteador do jupyter sem o middleware de limite de tentativas (ratelimit)")
for e in erros:
    print(f"::error::{ambiente}: {e}")
sys.exit(1 if erros else 0)
PY
  rm -f "$resolvido"
}

validar hml hml
validar prod 1.0

if [ "$falhou" -ne 0 ]; then
  echo "check-stack: o stack não passou na validação (veja os erros acima)." >&2
  exit 1
fi
echo "check-stack: ${STACK} válido para hml e prod"
