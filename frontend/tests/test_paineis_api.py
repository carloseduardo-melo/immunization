"""RF17/RF18 - Montagem dos parâmetros das chamadas dos dois painéis novos."""

from unittest.mock import patch

from api_client import obter_alta_complexidade, obter_sazonalidade


@patch("api_client._request")
def test_sazonalidade_sem_filtros_nao_envia_parametros(mock_request):
    mock_request.return_value = {"meses": []}

    obter_sazonalidade("tk")

    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/sazonalidade"
    assert kwargs["params"] == {}


@patch("api_client._request")
def test_sazonalidade_envia_todos_os_filtros(mock_request):
    mock_request.return_value = {"meses": []}

    obter_sazonalidade(
        "tk", vacina_id=7, municipio_id="2304400", ano_inicio=2023, ano_fim=2024
    )

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {
        "vacina_id": 7,
        "municipio_id": "2304400",
        "ano_inicio": 2023,
        "ano_fim": 2024,
    }


@patch("api_client._request")
def test_alta_complexidade_envia_o_top_municipios(mock_request):
    mock_request.return_value = {"items": []}

    obter_alta_complexidade("tk", top_municipios=5)

    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/alta-complexidade"
    assert kwargs["params"] == {"top_municipios": 5}


@patch("api_client._request")
def test_alta_complexidade_tem_padrao_de_tres(mock_request):
    mock_request.return_value = {"items": []}

    obter_alta_complexidade("tk")

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {"top_municipios": 3}
