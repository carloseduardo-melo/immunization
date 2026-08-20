from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def _resumo_dashboard():
    return {
        "kpis": {
            "total_doses": 100,
            "total_deslocamentos": 20,
            "taxa_mobilidade": 20.0,
            "total_inconsistentes": 1,
        },
        "grafico": [{"mes": "2024-01", "deslocou": True, "total": 20}],
    }


def _fluxo_intermunicipal(page: int = 1, page_size: int = 25):
    return {
        "items": [
            {
                "municipio_origem_id": "2303709",
                "municipio_origem_nome": "Caucaia",
                "municipio_destino_id": "2304400",
                "municipio_destino_nome": "Fortaleza",
                "total_doses": 7,
            },
            {
                "municipio_origem_id": "2308009",
                "municipio_origem_nome": "Maracanaú",
                "municipio_destino_id": "2304400",
                "municipio_destino_nome": "Fortaleza",
                "total_doses": 5,
            },
        ],
        "total": 38873,
        "page": page,
        "page_size": page_size,
        "total_pages": 1555,
        "total_doses": 900000,
    }


def _ranking_fluxo():
    return {
        "top_polo": [
            {
                "municipio_id": "2304400",
                "municipio_nome": "Fortaleza",
                "total_recebido": 7,
                "total_perdido": 0,
                "saldo_liquido": 7,
            }
        ],
        "top_evasao": [
            {
                "municipio_id": "2303709",
                "municipio_nome": "Caucaia",
                "total_recebido": 0,
                "total_perdido": 7,
                "saldo_liquido": -7,
            }
        ],
    }


_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]
_VACINAS = [(1, "COVID-19")]


@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_dashboard_exibe_ranking_abaixo_do_grafico_sem_erro(
    mock_mun_dash, mock_vac_dash, mock_resumo, mock_mun_fluxo, mock_vac_fluxo, mock_ranking
):
    mock_mun_dash.return_value = _MUNICIPIOS
    mock_vac_dash.return_value = _VACINAS
    mock_resumo.return_value = _resumo_dashboard()
    mock_mun_fluxo.return_value = _MUNICIPIOS
    mock_vac_fluxo.return_value = _VACINAS
    mock_ranking.return_value = _ranking_fluxo()

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "dashboard"
    at.run()

    assert not at.exception
    assert mock_ranking.called

    titulos = [m.value for m in at.markdown if "Ranking de municípios" in (m.value or "")]
    assert titulos, "Título do ranking não encontrado na página do Dashboard"


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_pagina_fluxo_intermunicipal_e_navegacao_propria(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _fluxo_intermunicipal()

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "fluxo"
    at.run()

    assert not at.exception
    assert mock_fluxo.called

    titulos = [m.value for m in at.markdown if "Fluxo Intermunicipal" in (m.value or "")]
    assert titulos, "Título da página de Fluxo Intermunicipal não encontrado"


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_nunca_pede_todos_os_pares_a_api(mock_mun, mock_vac, mock_fluxo):
    """Regressão do MessageSizeError: a tela precisa pedir páginas pequenas,
    nunca os ~39 mil pares de uma vez."""
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _fluxo_intermunicipal()

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "fluxo"
    at.run()

    assert not at.exception
    assert mock_fluxo.call_count >= 1
    for chamada in mock_fluxo.call_args_list:
        page_size = chamada.kwargs.get("page_size")
        assert page_size is not None, "page_size deve ser sempre explícito"
        assert page_size <= 100, f"page_size={page_size} traria dados demais para o navegador"
