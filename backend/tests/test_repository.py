import pytest

from app.repository import FiltroNaoPermitido, GoldRepository
from app.tables import CASOS_PROVAVEIS_UF_SEMANAL


def _repo():
    return GoldRepository(client=None, project="proj", dataset="gold", max_bytes_billed=10)


def test_filtro_vira_parametro_e_nao_sql():
    malicioso = "' OR 1=1 --"
    sql, params = _repo().montar_consulta(CASOS_PROVAVEIS_UF_SEMANAL, {"uf": malicioso}, 100, 0)
    assert malicioso not in sql
    assert "AND uf = @uf" in sql
    assert {p.name: p.value for p in params}["uf"] == malicioso
    assert {p.name: p.type_ for p in params}["uf"] == "STRING"


def test_ordem_paginacao_e_tabela():
    sql, params = _repo().montar_consulta(
        CASOS_PROVAVEIS_UF_SEMANAL, {"uf": None, "epi_year": 2024}, 1000, 2000
    )
    assert "FROM `proj.gold.gold_dengue_casos_provaveis_uf_semanal`" in sql
    assert "ORDER BY week_start, uf" in sql
    assert sql.endswith("LIMIT @limit OFFSET @offset")
    valores = {p.name: p.value for p in params}
    assert valores == {"epi_year": 2024, "limit": 1000, "offset": 2000}  # filtro None não entra


def test_coluna_fora_da_whitelist():
    with pytest.raises(FiltroNaoPermitido):
        _repo().montar_consulta(CASOS_PROVAVEIS_UF_SEMANAL, {"population": 1}, 10, 0)
