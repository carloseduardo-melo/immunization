"""RF19 - Cliente HTTP do download de CSV (/exportacoes/*)."""

from unittest.mock import MagicMock, patch

import pytest

from api_client import ApiError, exportar_csv, exportar_pdf


def _mock_response(status_code=200, conteudo=b"Data;Vacina\r\n", truncado="false"):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = conteudo
    mock.headers = {"X-Export-Truncated": truncado}
    return mock


@patch("api_client.requests.request")
def test_exportar_csv_devolve_o_conteudo_do_arquivo(mock_request):
    mock_request.return_value = _mock_response(conteudo=b"Data;Vacina\r\n01/01/2024;BCG\r\n")

    conteudo, truncado = exportar_csv("token123", "registros")

    assert conteudo == b"Data;Vacina\r\n01/01/2024;BCG\r\n"
    assert truncado is False
    assert mock_request.call_args.args == ("GET", "http://localhost:8000/exportacoes/registros")
    assert mock_request.call_args.kwargs["headers"]["Authorization"] == "Bearer token123"


@patch("api_client.requests.request")
def test_exportar_csv_repassa_os_filtros_da_tela(mock_request):
    mock_request.return_value = _mock_response()

    exportar_csv(
        "token123",
        "registros",
        municipio_id="2304400",
        vacina_id=3,
        data_inicio="2024-01-01",
        search="",
        idade_min=None,
    )

    # Filtro vazio ou ausente não vira query param: senão o backend receberia
    # um recorte diferente do que a tela está mostrando.
    assert mock_request.call_args.kwargs["params"] == {
        "municipio_id": "2304400",
        "vacina_id": 3,
        "data_inicio": "2024-01-01",
    }


@patch("api_client.requests.request")
def test_exportar_csv_envia_booleano_no_formato_da_api(mock_request):
    mock_request.return_value = _mock_response()

    exportar_csv("token123", "vacinas", alta_complexidade=True, ativo=False)

    assert mock_request.call_args.kwargs["params"] == {
        "alta_complexidade": "true",
        "ativo": "false",
    }


@patch("api_client.requests.request")
def test_exportar_csv_sinaliza_truncamento_pelo_cabecalho(mock_request):
    mock_request.return_value = _mock_response(truncado="true")

    _, truncado = exportar_csv("token123", "registros")

    assert truncado is True


@patch("api_client.requests.request")
def test_exportar_csv_usa_timeout_maior_que_o_padrao(mock_request):
    mock_request.return_value = _mock_response()

    exportar_csv("token123", "registros")

    # A exportação varre o recorte inteiro; 10s (padrão) estoura na base real.
    assert mock_request.call_args.kwargs["timeout"] == 120


@patch("api_client.requests.request")
def test_exportar_csv_propaga_erro_da_api(mock_request):
    resposta = _mock_response(status_code=401)
    resposta.json.return_value = {"detail": "Token ausente ou inválido."}
    mock_request.return_value = resposta

    with pytest.raises(ApiError) as erro:
        exportar_csv("token123", "registros")

    assert erro.value.status_code == 401


# ============================================================
# RELATÓRIO EM PDF (RF20)
# ============================================================


@patch("api_client.requests.request")
def test_exportar_pdf_devolve_o_conteudo_do_arquivo(mock_request):
    mock_request.return_value = _mock_response(conteudo=b"%PDF-1.4 fake")

    conteudo, truncado = exportar_pdf("token123", "registros")

    assert conteudo == b"%PDF-1.4 fake"
    assert truncado is False
    assert mock_request.call_args.args == (
        "GET",
        "http://localhost:8000/relatorios/registros",
    )


@patch("api_client.requests.request")
def test_exportar_pdf_repassa_os_filtros_da_tela(mock_request):
    mock_request.return_value = _mock_response(conteudo=b"%PDF-1.4 fake")

    exportar_pdf(
        "token123",
        "completude",
        status="ABERTO",
        municipio_id="2304400",
        ano=None,
    )

    assert mock_request.call_args.kwargs["params"] == {
        "status": "ABERTO",
        "municipio_id": "2304400",
    }


@patch("api_client.requests.request")
def test_exportar_pdf_sinaliza_truncamento_pelo_cabecalho(mock_request):
    mock_request.return_value = _mock_response(conteudo=b"%PDF-", truncado="true")

    _, truncado = exportar_pdf("token123", "registros")

    assert truncado is True


@patch("api_client.requests.request")
def test_exportar_pdf_usa_timeout_maior_que_o_padrao(mock_request):
    mock_request.return_value = _mock_response(conteudo=b"%PDF-")

    exportar_pdf("token123", "registros")

    assert mock_request.call_args.kwargs["timeout"] == 120


@patch("api_client.requests.request")
def test_exportar_pdf_propaga_erro_da_api(mock_request):
    resposta = _mock_response(status_code=500, conteudo=b"")
    resposta.json.return_value = {"detail": "Erro ao processar a solicitação."}
    mock_request.return_value = resposta

    with pytest.raises(ApiError) as erro:
        exportar_pdf("token123", "registros")

    assert erro.value.status_code == 500
