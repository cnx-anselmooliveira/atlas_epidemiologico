import os

from atlas_ml.forecast import threads


def test_padrao_e_um_terco_dos_nucleos(monkeypatch):
    monkeypatch.delenv("ATLAS_THREADS", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert threads.threads() == 2
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    assert threads.threads() == 1  # nunca zero


def test_variavel_muda_o_valor_e_valor_invalido_cai_no_padrao(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 9)
    monkeypatch.setenv("ATLAS_THREADS", "5")
    assert threads.threads() == 5
    for ruim in ("0", "-1", "abc", ""):
        monkeypatch.setenv("ATLAS_THREADS", ruim)
        assert threads.threads() == 3


def test_limitar_define_as_bibliotecas_sem_sobrescrever(monkeypatch):
    for nome in threads.VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("ATLAS_THREADS", "2")
    monkeypatch.setenv("MKL_NUM_THREADS", "4")  # quem já escolheu, mantém
    assert threads.limitar() == 2
    assert os.environ["OMP_NUM_THREADS"] == "2" and os.environ["MKL_NUM_THREADS"] == "4"
