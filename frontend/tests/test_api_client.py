from unittest.mock import MagicMock, patch

from api_client import (
    ApiError,
    _request,
    atualizar_municipio,
    criar_municipio,
    desativar_municipio,
    listar_municipios,
    listar_todos_municipios,
)


def _mock_response(status_code=200, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = b"{}"
    mock.json.return_value = json_data or {}
    return mock


@patch("api_client.requests.request")
def test_request_aceita_timeout_customizado_sem_conflitar_com_kwargs(mock_request):
    # _request tinha timeout=10 fixo e **kwargs adiante: um chamador que
    # tentasse _request(..., timeout=120) recebia
    # "TypeError: got multiple values for keyword argument 'timeout'".
    mock_request.return_value = _mock_response(200, {"ok": True})

    resultado = _request("GET", "/x", "token123", timeout=120)

    assert resultado == {"ok": True}
    assert mock_request.call_args.kwargs["timeout"] == 120


@patch("api_client.requests.request")
def test_request_usa_timeout_padrao_de_10s(mock_request):
    mock_request.return_value = _mock_response(200, {"ok": True})

    _request("GET", "/x", "token123")

    assert mock_request.call_args.kwargs["timeout"] == 10


@patch("api_client.requests.request")
def test_listar_municipios_monta_query_params(mock_request):
    mock_request.return_value = _mock_response(
        200, {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
    )

    resultado = listar_municipios("token123", uf="CE", ativo=True, search="fort", page=2, page_size=10)

    assert resultado["total"] == 0
    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {
        "page": 2, "page_size": 10, "uf": "CE", "ativo": "true", "search": "fort",
    }
    assert called_kwargs["headers"]["Authorization"] == "Bearer token123"


@patch("api_client.requests.request")
def test_listar_todos_municipios_percorre_todas_as_paginas(mock_request):
    pagina_1 = _mock_response(
        200,
        {
            "items": [{"nome": f"Municipio A{i}", "id_ibge": str(i)} for i in range(100)],
            "total": 184,
            "page": 1,
            "page_size": 100,
            "total_pages": 2,
        },
    )
    pagina_2 = _mock_response(
        200,
        {
            "items": [{"nome": f"Municipio Z{i}", "id_ibge": str(100 + i)} for i in range(84)],
            "total": 184,
            "page": 2,
            "page_size": 100,
            "total_pages": 2,
        },
    )
    mock_request.side_effect = [pagina_1, pagina_2]

    resultado = listar_todos_municipios("token123")

    assert len(resultado) == 184
    assert resultado[-1]["nome"] == "Municipio Z83"
    assert mock_request.call_count == 2


@patch("api_client.requests.request")
def test_criar_municipio_sucesso(mock_request):
    mock_request.return_value = _mock_response(201, {"id_ibge": "2304400", "nome": "Fortaleza"})

    resultado = criar_municipio("token123", {"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE"})

    assert resultado["nome"] == "Fortaleza"


@patch("api_client.requests.request")
def test_criar_municipio_erro_levanta_api_error(mock_request):
    mock_request.return_value = _mock_response(
        409, {"detail": "Já existe um município cadastrado com este código IBGE."}
    )

    try:
        criar_municipio("token123", {"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE"})
        assert False, "deveria ter levantado ApiError"
    except ApiError as exc:
        assert exc.status_code == 409
        assert "código IBGE" in exc.message


@patch("api_client.requests.request")
def test_atualizar_municipio(mock_request):
    mock_request.return_value = _mock_response(200, {"id_ibge": "2304400", "nome": "Nova"})

    resultado = atualizar_municipio("token123", "2304400", {"nome": "Nova", "uf": "CE"})

    assert resultado["nome"] == "Nova"
    assert mock_request.call_args.args[0] == "PUT"


@patch("api_client.requests.request")
def test_desativar_municipio(mock_request):
    mock_request.return_value = _mock_response(200, {"id_ibge": "2304400", "ativo": False})

    resultado = desativar_municipio("token123", "2304400")

    assert resultado["ativo"] is False
    assert mock_request.call_args.args[0] == "DELETE"


@patch("api_client.requests.request")
def test_listar_registros_monta_query_params(mock_request):
    from api_client import listar_registros

    mock_request.return_value = _mock_response(
        200, {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
    )

    resultado = listar_registros(
        "token123",
        municipio_id="2304400",
        vacina_id=1,
        data_inicio="2024-01-01",
        data_fim="2024-12-31",
        idade_min=18,
        idade_max=60,
        status_dado="VALIDO",
        page=1,
        page_size=10,
    )

    assert resultado["total"] == 0
    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {
        "page": 1,
        "page_size": 10,
        "municipio_id": "2304400",
        "vacina_id": 1,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
        "idade_min": 18,
        "idade_max": 60,
        "status_dado": "VALIDO",
    }
    assert called_kwargs["headers"]["Authorization"] == "Bearer token123"


@patch("api_client.requests.request")
def test_listar_registros_preserva_idade_min_zero(mock_request):
    from api_client import listar_registros

    mock_request.return_value = _mock_response(
        200, {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}
    )

    listar_registros("token123", page_size=5, idade_min=0, idade_max=10)

    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"].get("idade_min") == 0


@patch("api_client.requests.request")
def test_criar_registro_sucesso(mock_request):
    from api_client import criar_registro

    mock_request.return_value = _mock_response(
        201, {"id": "1234-uuid", "status_dado": "VALIDO", "teve_deslocamento": True}
    )

    payload = {
        "data_vacinacao": "2024-05-20",
        "municipio_vacina_id": "2304400",
        "municipio_residencia_id": "2303709",
        "vacina_id": 1,
        "idade": 25,
        "quantidade": 1,
    }

    resultado = criar_registro("token123", payload)

    assert resultado["status_dado"] == "VALIDO"
    assert mock_request.call_args.args[0] == "POST"
    assert mock_request.call_args.args[1] == "http://localhost:8000/registros"


# --- FLUXO INTERMUNICIPAL (RF13 & RF14) ---

@patch("api_client.requests.request")
def test_obter_fluxo_intermunicipal_monta_query_params(mock_request):
    from api_client import obter_fluxo_intermunicipal

    mock_request.return_value = _mock_response(200, {"items": []})

    resultado = obter_fluxo_intermunicipal(
        "token123",
        vacina_id=1,
        data_inicio="2024-01-01",
        data_fim="2024-12-31",
        municipio_id="2304400",
        page=2,
        page_size=50,
    )

    assert resultado["items"] == []
    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {
        "page": 2,
        "page_size": 50,
        "vacina_id": 1,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
        "municipio_id": "2304400",
    }
    assert mock_request.call_args.args[1] == "http://localhost:8000/fluxo/intermunicipal"


@patch("api_client.requests.request")
def test_obter_fluxo_intermunicipal_sempre_pagina(mock_request):
    """Sem filtros, a chamada ainda precisa enviar page/page_size — nunca pedir
    o conjunto completo de pares."""
    from api_client import obter_fluxo_intermunicipal

    mock_request.return_value = _mock_response(200, {"items": []})

    obter_fluxo_intermunicipal("token123")

    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {"page": 1, "page_size": 25}


@patch("api_client.requests.request")
def test_obter_ranking_fluxo_monta_query_params(mock_request):
    from api_client import obter_ranking_fluxo

    mock_request.return_value = _mock_response(200, {"top_polo": [], "top_evasao": []})

    resultado = obter_ranking_fluxo("token123", vacina_id=2, limit=5)

    assert resultado["top_polo"] == []
    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {"limit": 5, "vacina_id": 2}
    assert mock_request.call_args.args[1] == "http://localhost:8000/fluxo/ranking"


@patch("api_client.requests.request")
def test_obter_ranking_fluxo_usa_limit_padrao(mock_request):
    from api_client import obter_ranking_fluxo

    mock_request.return_value = _mock_response(200, {"top_polo": [], "top_evasao": []})

    obter_ranking_fluxo("token123")

    called_kwargs = mock_request.call_args.kwargs
    assert called_kwargs["params"] == {"limit": 10}


