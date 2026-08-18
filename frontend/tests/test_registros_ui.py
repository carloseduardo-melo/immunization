from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from registros_ui import _montar_filtros_query


def test_filtro_municipio_extrai_id_ibge():
    params = _montar_filtros_query("Fortaleza (2304400)", "Vacina: todas", "Período: 2024", "Faixa etária: todas")
    assert params["municipio_id"] == "2304400"


def test_filtro_vacina_extrai_id():
    params = _montar_filtros_query("Município: todos", "BCG (ID: 3)", "Período: 2024", "Faixa etária: todas")
    assert params["vacina_id"] == 3


def test_filtro_periodo_converte_para_intervalo_de_datas():
    params = _montar_filtros_query("Município: todos", "Vacina: todas", "Período: 2023", "Faixa etária: todas")
    assert params["data_inicio"] == "2023-01-01"
    assert params["data_fim"] == "2023-12-31"


def test_filtro_idade_converte_para_min_max():
    params = _montar_filtros_query("Município: todos", "Vacina: todas", "Período: 2024", "11-20 anos")
    assert params["idade_min"] == 11
    assert params["idade_max"] == 20


def test_filtros_todos_nao_aplicam_municipio_vacina_nem_idade():
    params = _montar_filtros_query("Município: todos", "Vacina: todas", "Período: 2024", "Faixa etária: todas")
    assert "municipio_id" not in params
    assert "vacina_id" not in params
    assert "idade_min" not in params
    assert "idade_max" not in params


def _resultado_vazio():
    return {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}


@patch("registros_ui.listar_vacinas")
@patch("registros_ui.listar_todos_municipios")
@patch("registros_ui.listar_registros")
def test_selecionar_filtro_municipio_repassa_municipio_id_para_api(
    mock_listar_registros, mock_listar_municipios, mock_listar_vacinas
):
    mock_listar_registros.return_value = _resultado_vazio()
    mock_listar_municipios.return_value = [{"nome": "Fortaleza", "id_ibge": "2304400"}]
    mock_listar_vacinas.return_value = {"items": []}

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "registros"
    at.session_state["dados_municipios"] = [{"nome": "Fortaleza", "id_ibge": "2304400"}]
    at.session_state["filtro_mun"] = "Fortaleza (2304400)"
    at.run()

    assert not at.exception
    called_kwargs = mock_listar_registros.call_args.kwargs
    assert called_kwargs.get("municipio_id") == "2304400"
