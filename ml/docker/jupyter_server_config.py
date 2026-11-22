"""Configuração do Jupyter Server da imagem `notebook` (lida de /etc/jupyter pelo servidor).

Dois modos, escolhidos pelo ambiente do contêiner, e nenhum deles sobe aberto:

- **Stack (hml e prod):** a variável `JUPYTER_PASSWORD_HASH` traz o HASH da senha (argon2, gerado por
  `jupyter_server.auth.passwd`). Ela precisa estar preenchida e parecer um hash (uma senha em texto é
  recusada). O token fica desligado. Só o hash vai para o stack: a senha em texto fica com quem a escolheu.
- **Dev:** sem essa variável, `JUPYTER_TOKEN` é obrigatório (não há valor padrão).

Em qualquer modo: terminal desativado, sem root, proxy aceito (o Traefik fica na frente) e a pasta de
trabalho no volume do usuário.
"""

import os
import re

c = get_config()  # noqa: F821  (injetado pelo Jupyter ao ler este arquivo)

HASH_VALIDO = re.compile(r"^(argon2:|sha1:|sha256:|sha512:|pbkdf2:)\S+$")


def _falhar(mensagem: str):
    raise SystemExit(f"jupyter: {mensagem}")


# presente (mesmo vazia) = modo stack: um valor vazio ou estragado falha em vez de cair no modo dev
senha_hash = os.environ.get("JUPYTER_PASSWORD_HASH")
if senha_hash is not None:
    senha_hash = senha_hash.strip()
    if len(senha_hash) > 1 and senha_hash[0] == senha_hash[-1] and senha_hash[0] in "'\"":
        senha_hash = senha_hash[1:-1].strip()  # um .env lido sem tirar as aspas (docker --env-file)
    if not senha_hash:
        _falhar("JUPYTER_PASSWORD_HASH está vazia (defina o hash da senha no stack)")
    if not HASH_VALIDO.match(senha_hash):
        _falhar(
            "JUPYTER_PASSWORD_HASH não parece um hash de senha do Jupyter (argon2:...). Use só o hash, "
            "gerado por jupyter_server.auth.passwd, e nunca a senha em texto. No .env, o valor vai entre "
            "aspas simples por causa do '$'."
        )
    c.PasswordIdentityProvider.hashed_password = senha_hash
    c.PasswordIdentityProvider.password_required = True
    c.IdentityProvider.token = ""  # sem token: só a senha
else:
    token = os.environ.get("JUPYTER_TOKEN", "").strip()
    if not token:
        _falhar("JUPYTER_TOKEN é obrigatório no dev (sem token padrão). No stack use JUPYTER_PASSWORD_HASH")
    c.IdentityProvider.token = token

c.ServerApp.terminals_enabled = False
c.ServerApp.allow_root = False
c.ServerApp.open_browser = False
c.ServerApp.trust_xheaders = True  # o Traefik repassa X-Forwarded-*
c.ServerApp.allow_remote_access = True
c.ServerApp.root_dir = os.environ.get("JUPYTER_ROOT_DIR", "/home/atlas/work")
