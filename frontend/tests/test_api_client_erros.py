"""Cobre os caminhos de erro do cliente HTTP e os wrappers ainda sem teste."""

from unittest.mock import MagicMock, patch

import pytest
import requests

import api_client
from api_client import ApiError


def _resp(status_code=200, json_data=None, content=b"{}"):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = content
    mock.json.return_value = json_data if json_data is not None else {}
    return mock


# --- tratamento de falhas de rede ---------------------------------------

@pytest.mark.parametrize(
    "excecao, trecho_esperado",
    [
        (requests.exceptions.ConnectionError(), "conectar"),
        (requests.exceptions.Timeout(), "demorou"),
        (requests.exceptions.RequestException(), "comunicação"),
    ],
)
@patch("api_client.requests.request")
def test_falhas_de_rede_viram_api_error(mock_request, excecao, trecho_esperado):
    mock_request.side_effect = excecao

    with pytest.raises(ApiError) as exc:
        api_client.obter_me("token")

    assert trecho_esperado in exc.value.message


@patch("api_client.requests.request")
def test_erro_http_com_corpo_ilegivel_usa_mensagem_padrao(mock_request):
    resposta = _resp(500)
    resposta.json.side_effect = ValueError("corpo não é JSON")
    mock_request.return_value = resposta

    with pytest.raises(ApiError) as exc:
        api_client.obter_me("token")

    assert exc.value.status_code == 500
    assert "Erro ao processar a solicitação." in exc.value.message


@patch("api_client.requests.request")
def test_resposta_sem_conteudo_retorna_none(mock_request):
    mock_request.return_value = _resp(204, content=b"")

    assert api_client.desativar_registro("token", "abc") is None


@patch("api_client.requests.request")
def test_obter_me_usa_rota_de_autenticacao(mock_request):
    mock_request.return_value = _resp(200, {"email": "a@b.c", "role": "ADMIN"})

    assert api_client.obter_me("token")["role"] == "ADMIN"
    assert mock_request.call_args.args[1] == "http://localhost:8000/auth/me"


# --- vacinas -------------------------------------------------------------

@patch("api_client.requests.request")
def test_listar_vacinas_monta_todos_os_filtros(mock_request):
    mock_request.return_value = _resp(200, {"items": []})

    api_client.listar_vacinas(
        "token", alta_complexidade=True, ativo=False, search="cov", page=2, page_size=20
    )

    assert mock_request.call_args.kwargs["params"] == {
        "page": 2,
        "page_size": 20,
        "alta_complexidade": "true",
        "ativo": "false",
        "search": "cov",
    }


@patch("api_client.requests.request")
def test_crud_de_vacina_usa_metodo_e_rota_corretos(mock_request):
    mock_request.return_value = _resp(200, {"id": 1})

    api_client.criar_vacina("token", {"nome": "BCG"})
    assert mock_request.call_args.args[0] == "POST"

    api_client.atualizar_vacina("token", 1, {"nome": "BCG"})
    assert mock_request.call_args.args[0] == "PUT"
    assert mock_request.call_args.args[1].endswith("/vacinas/1")

    api_client.desativar_vacina("token", 1)
    assert mock_request.call_args.args[0] == "DELETE"


# --- registros -----------------------------------------------------------

@patch("api_client.requests.request")
def test_listar_registros_com_busca(mock_request):
    mock_request.return_value = _resp(200, {"items": []})

    api_client.listar_registros("token", search="fortaleza")

    assert mock_request.call_args.kwargs["params"]["search"] == "fortaleza"


@patch("api_client.requests.request")
def test_atualizar_e_desativar_registro(mock_request):
    mock_request.return_value = _resp(200, {"id": "uuid-1"})

    api_client.atualizar_registro("token", "uuid-1", {"quantidade": 2})
    assert mock_request.call_args.args[0] == "PUT"
    assert mock_request.call_args.args[1].endswith("/registros/uuid-1")

    api_client.desativar_registro("token", "uuid-1")
    assert mock_request.call_args.args[0] == "DELETE"


# --- municipios ----------------------------------------------------------

@patch("api_client.requests.request")
def test_listar_municipios_sem_filtros_opcionais(mock_request):
    mock_request.return_value = _resp(
        200, {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
    )

    api_client.listar_municipios("token")

    assert mock_request.call_args.kwargs["params"] == {"page": 1, "page_size": 10}


@patch("api_client.requests.request")
def test_listar_todos_municipios_para_em_uma_unica_pagina(mock_request):
    mock_request.return_value = _resp(
        200,
        {
            "items": [{"id_ibge": "2304400", "nome": "Fortaleza"}],
            "total": 1,
            "page": 1,
            "page_size": 100,
            "total_pages": 1,
        },
    )

    assert len(api_client.listar_todos_municipios("token")) == 1
    assert mock_request.call_count == 1


# --- dashboard e fluxo ---------------------------------------------------

@patch("api_client.requests.request")
def test_resumo_dashboard_monta_filtros(mock_request):
    mock_request.return_value = _resp(200, {"kpis": {}, "grafico": []})

    api_client.obter_resumo_dashboard("token", municipio_id="2304400", vacina_id=1, ano=2024)

    assert mock_request.call_args.kwargs["params"] == {
        "municipio_id": "2304400",
        "vacina_id": 1,
        "ano": 2024,
    }


@patch("api_client.requests.request")
def test_resumo_dashboard_sem_filtros(mock_request):
    mock_request.return_value = _resp(200, {"kpis": {}, "grafico": []})

    api_client.obter_resumo_dashboard("token")

    assert mock_request.call_args.kwargs["params"] == {}


@patch("api_client.requests.request")
def test_ranking_monta_todos_os_filtros(mock_request):
    mock_request.return_value = _resp(200, {"top_polo": [], "top_evasao": []})

    api_client.obter_ranking_fluxo(
        "token", vacina_id=3, data_inicio="2024-01-01", data_fim="2024-12-31", limit=5
    )

    assert mock_request.call_args.kwargs["params"] == {
        "limit": 5,
        "vacina_id": 3,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
    }
