"""RF22 - Montagem dos parâmetros das chamadas ao log de auditoria."""

from unittest.mock import patch

from api_client import listar_logs_auditoria, listar_usuarios_auditoria


@patch("api_client._request")
def test_sem_filtros_envia_apenas_a_paginacao(mock_request):
    mock_request.return_value = {"items": []}

    listar_logs_auditoria("tk")

    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/auditoria"
    assert kwargs["params"] == {"page": 1, "page_size": 10}


@patch("api_client._request")
def test_envia_todos_os_filtros(mock_request):
    mock_request.return_value = {"items": []}

    listar_logs_auditoria(
        "tk",
        usuario_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        tabela="vacinas",
        data_inicio="2026-08-01",
        data_fim="2026-08-31",
        page=3,
        page_size=25,
    )

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {
        "page": 3,
        "page_size": 25,
        "usuario_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "tabela": "vacinas",
        "data_inicio": "2026-08-01",
        "data_fim": "2026-08-31",
    }


@patch("api_client._request")
def test_filtros_vazios_nao_viram_parametro(mock_request):
    mock_request.return_value = {"items": []}

    listar_logs_auditoria("tk", usuario_id="", tabela="", data_inicio="", data_fim="")

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {"page": 1, "page_size": 10}


@patch("api_client._request")
def test_lista_de_autores_usa_o_endpoint_proprio(mock_request):
    mock_request.return_value = []

    assert listar_usuarios_auditoria("tk") == []

    args, _ = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/auditoria/usuarios"
