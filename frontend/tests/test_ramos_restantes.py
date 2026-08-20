"""Fecha os ramos restantes: paginação para trás, filtros do dashboard,
listas de apoio indisponíveis e os estados parciais do ranking."""

from unittest.mock import MagicMock, patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]
_VACINAS = [(1, "COVID-19")]


@pytest.fixture
def cookies():
    with patch("streamlit_cookies_controller.CookieController") as controlador:
        instancia = MagicMock()
        instancia.get.return_value = None
        controlador.return_value = instancia
        yield instancia


def _app(pagina, **estado):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = pagina
    for chave, valor in estado.items():
        at.session_state[chave] = valor
    return at


def _lista_municipios():
    return {
        "items": [{"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
                   "regiao_saude": None, "polo": True, "ativo": True}],
        "total": 9, "page": 2, "page_size": 3, "total_pages": 3,
    }


def _lista_vacinas():
    return {
        "items": [{"id": 1, "nome": "COVID-19", "alta_complexidade": False, "ativo": True}],
        "total": 9, "page": 2, "page_size": 3, "total_pages": 3,
    }


def _resumo():
    return {
        "kpis": {"total_doses": 10, "total_deslocamentos": 2,
                 "taxa_mobilidade": 20.0, "total_inconsistentes": 0},
        "grafico": [{"mes": "2024-01", "deslocou": True, "total": 2}],
    }


# --- paginação para trás ------------------------------------------------

@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_pagina_anterior_de_municipios_e_vacinas(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios", municipios_page=2)
    at.run()
    at.button(key="prev_mun").click().run()
    assert at.session_state["municipios_page"] == 1

    at2 = _app("municipios", vacinas_page=2)
    at2.run()
    at2.button(key="prev_vac").click().run()
    assert at2.session_state["vacinas_page"] == 1
    assert not at2.exception


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_pagina_anterior_de_registros(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {
        "items": [], "total": 20, "page": 2, "page_size": 5, "total_pages": 4,
    }

    at = _app("registros", reg_page=2)
    at.run()
    at.button(key="prev_reg").click().run()

    assert not at.exception
    assert at.session_state["reg_page"] == 1


# --- cancelar edição de vacina ------------------------------------------

@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cancelar_edicao_de_vacina_limpa_o_estado(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios", vacina_editando={"id": 1, "nome": "COVID-19",
                                             "alta_complexidade": False, "ativo": True})
    at.run()
    at.button(key="FormSubmitter:form_vacina-Cancelar").click().run()

    assert not at.exception
    assert at.session_state["vacina_editando"] is None


@patch("municipios_ui.criar_vacina")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_erro_da_api_ao_salvar_vacina(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()
    mock_criar.side_effect = ApiError("Vacina já cadastrada.")

    at = _app("municipios")
    at.run()
    at.text_input[2].set_value("BCG")
    at.button(key="FormSubmitter:form_vacina-Salvar").click().run()

    assert not at.exception
    assert any("Vacina já cadastrada." in e.value for e in at.error)


# --- listas de apoio indisponíveis nos registros -------------------------

@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_registros_abre_mesmo_sem_listas_de_apoio(mock_mun, mock_vac, mock_reg):
    mock_mun.side_effect = ApiError("cadastro fora do ar")
    mock_vac.side_effect = ApiError("cadastro fora do ar")
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = _app("registros")
    at.run()

    assert not at.exception
    assert at.session_state["dados_municipios"] == []
    assert at.session_state["dados_vacinas"] == []


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_trocar_filtro_de_registros_volta_para_a_primeira_pagina(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = _app("registros", reg_page=3)
    at.run()
    # 0-2 são os selects do formulário; 3 é o filtro de município da listagem
    at.selectbox[3].select("Fortaleza (2304400)").run()

    assert not at.exception
    assert at.session_state["reg_page"] == 1
    assert at.session_state["filtro_mun"] == "Fortaleza (2304400)"


# --- filtros do dashboard ------------------------------------------------

@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_filtros_de_vacina_e_ano_do_dashboard(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    at = _app("dashboard")
    at.run()
    at.selectbox[1].select("COVID-19 (ID: 1)").run()
    at.selectbox[2].select("2024").run()

    assert not at.exception
    chamadas = mock_resumo.call_args_list
    assert any(c.kwargs.get("vacina_id") == 1 for c in chamadas)
    assert any(c.kwargs.get("ano") == 2024 for c in chamadas)


# --- ranking com apenas um dos lados preenchido --------------------------

@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_ranking_com_apenas_um_dos_lados(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    """Quando só há polos (ou só evasão), a outra coluna mostra 'Sem dados.'."""
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {
        "top_polo": [{"municipio_id": "2304400", "municipio_nome": "Fortaleza",
                      "total_recebido": 7, "total_perdido": 0, "saldo_liquido": 7}],
        "top_evasao": [],
    }

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("Sem dados." in c.value for c in at.caption)


# --- inicialização de sessão em app.py -----------------------------------

def test_app_inicializa_estado_sem_chaves_previas(cookies):
    """Primeira visita: nenhuma chave de sessão existe ainda."""
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()

    assert not at.exception
    assert at.session_state["token"] is None
    assert at.session_state["pagina_ativa"] == "dashboard"


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_pedido_de_limpeza_do_cookie_remove_o_token(mock_mun, mock_vac, mock_reg, cookies):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}
    cookies.get.return_value = "jwt-antigo"

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "jwt-abc"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "registros"
    at.session_state["_cookie_sync"] = "clear"
    at.run()

    assert not at.exception
    cookies.remove.assert_called_with("token")
    assert at.session_state["_cookie_sync"] is None


def test_render_direto_do_modulo_de_dashboard():
    """Cobre o guard `__main__` dos módulos de tela."""
    import ui_dashboard

    st.session_state.clear()
    ui_dashboard.render_dashboard_section()


@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_ranking_so_com_evasao(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    """Espelho do teste anterior: só há evasão, então a coluna de polos avisa."""
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {
        "top_polo": [],
        "top_evasao": [{"municipio_id": "2303709", "municipio_nome": "Caucaia",
                        "total_recebido": 0, "total_perdido": 7, "saldo_liquido": -7}],
    }

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("Sem dados." in c.value for c in at.caption)
