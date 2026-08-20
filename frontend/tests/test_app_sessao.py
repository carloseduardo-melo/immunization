"""Cobre o ciclo de sessão em app.py: login bem-sucedido, erros do servidor e
a restauração da sessão a partir do cookie do navegador.

O componente de cookies roda num iframe e não funciona fora do navegador, então
em todos os testes daqui ele é substituído por um dublê.
"""

from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def cookies():
    with patch("streamlit_cookies_controller.CookieController") as controlador:
        instancia = MagicMock()
        instancia.get.return_value = None
        controlador.return_value = instancia
        yield instancia


def _tela_de_login(cookies_mock=None):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()
    return at


def _preencher_e_entrar(at, email="gestor@saude.ce.gov.br", senha="segredo"):
    at.text_input[0].set_value(email)
    at.text_input[1].set_value(senha)
    return at.button[0].click().run()


@patch("requests.post")
def test_login_bem_sucedido_guarda_sessao_e_pede_cookie(mock_post, cookies):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "jwt-abc",
        "role": "GESTOR_ESTADUAL",
        "municipio_alocado_id": None,
    }

    at = _tela_de_login()
    _preencher_e_entrar(at)

    assert not at.exception
    assert at.session_state["token"] == "jwt-abc"
    assert at.session_state["role"] == "GESTOR_ESTADUAL"


@patch("requests.post")
def test_login_guarda_municipio_do_gestor_municipal(mock_post, cookies):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "access_token": "jwt-abc",
        "role": "GESTOR_MUNICIPAL",
        "municipio_alocado_id": "2304400",
    }

    at = _tela_de_login()
    _preencher_e_entrar(at)

    assert not at.exception
    assert at.session_state["municipio_id"] == "2304400"


@patch("requests.post")
def test_erro_inesperado_do_servidor_mostra_codigo(mock_post, cookies):
    mock_post.return_value.status_code = 500

    at = _tela_de_login()
    _preencher_e_entrar(at)

    assert not at.exception
    assert any("500" in e.value for e in at.error)


@patch("requests.post")
def test_timeout_no_login_mostra_mensagem(mock_post, cookies):
    import requests as _rq

    mock_post.side_effect = _rq.exceptions.Timeout()

    at = _tela_de_login()
    _preencher_e_entrar(at)

    assert not at.exception
    assert any("demorou" in e.value for e in at.error)


@patch("requests.post")
def test_falha_generica_de_rede_no_login(mock_post, cookies):
    import requests as _rq

    mock_post.side_effect = _rq.exceptions.RequestException()

    at = _tela_de_login()
    _preencher_e_entrar(at)

    assert not at.exception
    assert any("comunicação" in e.value for e in at.error)


@patch("api_client.requests.request")
def test_sessao_restaurada_a_partir_do_cookie(mock_request, cookies):
    """Com um cookie válido, a app revalida o token e entra direto."""
    cookies.get.return_value = "jwt-do-cookie"
    mock_request.return_value = MagicMock(
        status_code=200,
        content=b"{}",
        **{"json.return_value": {
            "email": "a@b.c", "role": "ADMIN", "municipio_alocado_id": None}},
    )

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()

    assert not at.exception
    assert at.session_state["token"] == "jwt-do-cookie"
    assert at.session_state["role"] == "ADMIN"


@patch("api_client.requests.request")
def test_cookie_invalido_e_removido_e_login_continua(mock_request, cookies):
    cookies.get.return_value = "jwt-expirado"
    mock_request.return_value = MagicMock(
        status_code=401,
        content=b"{}",
        **{"json.return_value": {"detail": "Token ausente ou inválido."}},
    )

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()

    assert not at.exception
    assert at.session_state["token"] is None
    cookies.remove.assert_called_with("token")
    assert any("Entrar na sua conta" in md.value for md in at.markdown)


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_cookie_pendente_de_gravacao_e_consumido(mock_mun, mock_vac, mock_reg, cookies):
    mock_mun.return_value = [("2304400", "Fortaleza")]
    mock_vac.return_value = [(1, "COVID-19")]
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "jwt-abc"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "registros"
    at.session_state["_cookie_sync"] = "set"
    at.run()

    assert not at.exception
    cookies.set.assert_called_with("token", "jwt-abc")
    assert at.session_state["_cookie_sync"] is None


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_navegacao_pela_sidebar_troca_de_pagina(mock_mun, mock_vac, mock_reg, cookies):
    mock_mun.return_value = [("2304400", "Fortaleza")]
    mock_vac.return_value = [(1, "COVID-19")]
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "jwt-abc"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "registros"
    at.run()

    at.sidebar.button(key="nav_municipios").click().run()

    assert not at.exception
    assert at.session_state["pagina_ativa"] == "municipios"
