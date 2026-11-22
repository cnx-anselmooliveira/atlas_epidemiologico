"""Configuração do servidor Jupyter e semeador do volume de trabalho (ml/docker), sem subir o servidor."""

import importlib.util
from pathlib import Path

import pytest

traitlets_config = pytest.importorskip("traitlets.config")

DOCKER = Path(__file__).resolve().parents[1] / "docker"
HASH = "argon2:$argon2id$v=19$m=10240,t=10,p=8$c2FsdHNhbHQ$ZGlnZXN0ZGlnZXN0ZGlnZXN0"


def carregar_config(monkeypatch, **env):
    """Executa o jupyter_server_config.py com um `get_config` falso e devolve a configuração resultante."""
    for chave in ("JUPYTER_PASSWORD_HASH", "JUPYTER_TOKEN", "JUPYTER_ROOT_DIR"):
        monkeypatch.delenv(chave, raising=False)
    for chave, valor in env.items():
        monkeypatch.setenv(chave, valor)
    c = traitlets_config.Config()
    codigo = (DOCKER / "jupyter_server_config.py").read_text(encoding="utf-8")
    exec(compile(codigo, "jupyter_server_config.py", "exec"), {"get_config": lambda: c})  # noqa: S102
    return c


def test_com_o_hash_define_a_senha_e_desliga_o_token(monkeypatch):
    c = carregar_config(
        monkeypatch, JUPYTER_PASSWORD_HASH="  " + HASH + "\n"
    )  # espaços das pontas são descartados
    assert c.PasswordIdentityProvider.hashed_password == HASH
    assert c.PasswordIdentityProvider.password_required is True
    assert c.IdentityProvider.token == ""  # nada de token no stack


def test_aspas_ao_redor_do_hash_sao_toleradas(monkeypatch):
    # `docker run --env-file` e alguns carregadores de .env entregam o valor com as aspas
    for valor in (f"'{HASH}'", f'"{HASH}"'):
        c = carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH=valor)
        assert c.PasswordIdentityProvider.hashed_password == HASH


def test_hash_vazio_nao_sobe_nem_cai_no_modo_dev(monkeypatch):
    with pytest.raises(SystemExit, match="JUPYTER_PASSWORD_HASH está vazia"):
        carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH="  ")
    with pytest.raises(SystemExit, match="JUPYTER_PASSWORD_HASH está vazia"):
        carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH="", JUPYTER_TOKEN="alguma-coisa")


def test_senha_em_texto_e_recusada(monkeypatch):
    with pytest.raises(SystemExit, match="não parece um hash de senha"):
        carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH="minha-senha-em-texto")


def test_hash_cortado_pelo_cifrao_e_recusado(monkeypatch):
    # o que sobra de um argon2 quando o ambiente interpreta o '$' como variável
    with pytest.raises(SystemExit, match="não parece um hash de senha"):
        carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH="argon2:")


def test_no_stack_um_token_por_engano_nao_contorna_o_hash(monkeypatch):
    c = carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH=HASH, JUPYTER_TOKEN="alguma-coisa")
    assert c.IdentityProvider.token == ""


def test_dev_exige_token_e_nao_tem_padrao(monkeypatch):
    with pytest.raises(SystemExit, match="JUPYTER_TOKEN é obrigatório"):
        carregar_config(monkeypatch)
    with pytest.raises(SystemExit, match="JUPYTER_TOKEN é obrigatório"):
        carregar_config(monkeypatch, JUPYTER_TOKEN="   ")
    assert (
        carregar_config(monkeypatch, JUPYTER_TOKEN="segredo-de-dev").IdentityProvider.token
        == "segredo-de-dev"
    )


@pytest.mark.parametrize("modo", ["senha", "token"])
def test_terminal_desligado_sem_root_e_com_proxy_em_qualquer_modo(monkeypatch, modo):
    if modo == "senha":
        c = carregar_config(monkeypatch, JUPYTER_PASSWORD_HASH=HASH, JUPYTER_ROOT_DIR="/home/atlas/work")
    else:
        c = carregar_config(monkeypatch, JUPYTER_TOKEN="t")
    assert c.ServerApp.terminals_enabled is False and c.ServerApp.allow_root is False
    assert c.ServerApp.trust_xheaders is True and c.ServerApp.allow_remote_access is True
    assert c.ServerApp.open_browser is False


def semeador():
    spec = importlib.util.spec_from_file_location("semear_notebooks", DOCKER / "semear_notebooks.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def criar(pasta: Path, **arquivos):
    for nome, conteudo in arquivos.items():
        (pasta / nome).parent.mkdir(parents=True, exist_ok=True)
        (pasta / nome).write_text(conteudo, encoding="utf-8")
    return pasta


def test_volume_vazio_recebe_os_notebooks_da_imagem(tmp_path):
    imagem = criar(tmp_path / "imagem", **{"svr/svr.ipynb": "da imagem", "svr/__pycache__/x.pyc": "lixo"})
    trabalho = tmp_path / "trabalho"
    assert semeador().semear(trabalho, imagem) == "imagem"
    assert (trabalho / "notebooks" / "svr" / "svr.ipynb").read_text(encoding="utf-8") == "da imagem"
    assert not (trabalho / "notebooks" / "svr" / "__pycache__").exists()


def test_o_clone_do_git_sync_nao_e_usado():
    # o Jupyter não tem integração com nada do projeto: não há outra origem além da imagem
    modulo = semeador()
    assert not hasattr(modulo, "CLONE")
    assert "clone" not in modulo.semear.__code__.co_varnames


def test_volume_com_trabalho_do_usuario_nao_e_sobrescrito(tmp_path):
    imagem = criar(tmp_path / "imagem", **{"svr/svr.ipynb": "da imagem"})
    trabalho = criar(tmp_path / "trabalho", **{"meu.ipynb": "trabalho do usuário"})
    assert semeador().semear(trabalho, imagem) == "nada"
    assert not (trabalho / "notebooks").exists()
    assert (trabalho / "meu.ipynb").read_text(encoding="utf-8") == "trabalho do usuário"


def test_lost_found_de_volume_novo_nao_conta_como_trabalho(tmp_path):
    imagem = criar(tmp_path / "imagem", **{"svr/svr.ipynb": "x"})
    trabalho = tmp_path / "trabalho"
    (trabalho / "lost+found").mkdir(parents=True)
    assert semeador().semear(trabalho, imagem) == "imagem"


def test_sem_a_copia_da_imagem_nao_faz_nada(tmp_path):
    assert semeador().semear(tmp_path / "trabalho", tmp_path / "b") == "nada"
