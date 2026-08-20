from unittest.mock import patch

from api_client import atualizar_status_alerta, listar_alertas_completude, recalcular_completude


@patch("api_client._request")
def test_listar_alertas_envia_apenas_os_filtros_preenchidos(mock_request):
    mock_request.return_value = {"items": []}

    listar_alertas_completude("tk", status="ABERTO", page=2, page_size=25)

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {"page": 2, "page_size": 25, "status": "ABERTO"}


@patch("api_client._request")
def test_listar_alertas_com_todos_os_filtros(mock_request):
    mock_request.return_value = {"items": []}

    listar_alertas_completude("tk", status="RESOLVIDO", municipio_id="2304400", ano=2024)

    _, kwargs = mock_request.call_args
    assert kwargs["params"]["municipio_id"] == "2304400"
    assert kwargs["params"]["ano"] == 2024


@patch("api_client._request")
def test_atualizar_status_usa_put_no_alerta(mock_request):
    mock_request.return_value = {"status": "RESOLVIDO"}

    atualizar_status_alerta("tk", "abc-123", "RESOLVIDO")

    args, kwargs = mock_request.call_args
    assert args[0] == "PUT"
    assert args[1] == "/completude/alertas/abc-123"
    assert kwargs["json"] == {"status": "RESOLVIDO"}


@patch("api_client._request")
def test_recalcular_envia_o_k(mock_request):
    mock_request.return_value = {"alertas_criados": 0}

    recalcular_completude("tk", k=3.0)

    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert kwargs["params"] == {"k": 3.0}
