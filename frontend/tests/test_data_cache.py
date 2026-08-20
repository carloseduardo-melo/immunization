"""Cobre a camada de cache: forma dos dados reduzidos e repasse de parâmetros."""

from unittest.mock import patch

import pytest

import data_cache


@pytest.fixture(autouse=True)
def _limpar_cache():
    """Sem isto, o valor memoizado de um teste vazaria para o seguinte."""
    for funcao in (
        data_cache.listar_municipios_resumido,
        data_cache.listar_vacinas_resumido,
        data_cache.fluxo_intermunicipal,
        data_cache.ranking_fluxo,
        data_cache.resumo_dashboard,
        data_cache.alertas_completude,
    ):
        funcao.clear()
    yield


@patch("data_cache.listar_todos_municipios")
def test_municipios_resumido_guarda_apenas_id_e_nome(mock_listar):
    mock_listar.return_value = [
        {
            "id_ibge": "2304400",
            "nome": "Fortaleza",
            "uf": "CE",
            "regiao_saude": "Região de Fortaleza",
            "polo": True,
            "ativo": True,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
    ]

    assert data_cache.listar_municipios_resumido("token") == [("2304400", "Fortaleza")]


@patch("data_cache.listar_todos_municipios")
def test_municipios_resumido_nao_repete_a_chamada_http(mock_listar):
    mock_listar.return_value = [{"id_ibge": "2304400", "nome": "Fortaleza"}]

    data_cache.listar_municipios_resumido("token")
    data_cache.listar_municipios_resumido("token")
    data_cache.listar_municipios_resumido("token")

    assert mock_listar.call_count == 1, "o cache deve evitar refazer a busca paginada"


@patch("data_cache.listar_todos_municipios")
def test_cache_e_separado_por_token(mock_listar):
    mock_listar.return_value = [{"id_ibge": "2304400", "nome": "Fortaleza"}]

    data_cache.listar_municipios_resumido("token-a")
    data_cache.listar_municipios_resumido("token-b")

    assert mock_listar.call_count == 2


@patch("data_cache.listar_vacinas")
def test_vacinas_resumido_guarda_apenas_id_e_nome(mock_listar):
    mock_listar.return_value = {
        "items": [{"id": 1, "nome": "COVID-19", "alta_complexidade": False, "ativo": True}]
    }

    assert data_cache.listar_vacinas_resumido("token") == [(1, "COVID-19")]


@patch("data_cache.obter_fluxo_intermunicipal")
def test_fluxo_repassa_todos_os_parametros(mock_fluxo):
    mock_fluxo.return_value = {"items": []}

    data_cache.fluxo_intermunicipal(
        "token",
        vacina_id=1,
        data_inicio="2024-01-01",
        data_fim="2024-12-31",
        municipio_id="2304400",
        page=3,
        page_size=50,
    )

    assert mock_fluxo.call_args.kwargs == {
        "vacina_id": 1,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
        "municipio_id": "2304400",
        "page": 3,
        "page_size": 50,
    }


@patch("data_cache.obter_ranking_fluxo")
def test_ranking_repassa_todos_os_parametros(mock_ranking):
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    data_cache.ranking_fluxo(
        "token", vacina_id=2, data_inicio="2024-01-01", data_fim="2024-12-31", limit=25
    )

    assert mock_ranking.call_args.kwargs == {
        "vacina_id": 2,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-12-31",
        "limit": 25,
    }


@patch("data_cache.obter_resumo_dashboard")
def test_resumo_dashboard_repassa_parametros(mock_resumo):
    mock_resumo.return_value = {"kpis": {}, "grafico": []}

    data_cache.resumo_dashboard("token", municipio_id="2304400", vacina_id=1, ano=2024)

    assert mock_resumo.call_args.kwargs == {
        "municipio_id": "2304400",
        "vacina_id": 1,
        "ano": 2024,
    }


@patch("data_cache.listar_alertas_completude")
def test_alertas_completude_repassa_todos_os_parametros(mock_listar):
    mock_listar.return_value = {"items": []}

    data_cache.alertas_completude(
        "token", status="ABERTO", municipio_id="2304400", ano=2024, page=2, page_size=25
    )

    assert mock_listar.call_args.kwargs == {
        "status": "ABERTO",
        "municipio_id": "2304400",
        "ano": 2024,
        "page": 2,
        "page_size": 25,
    }


@patch("data_cache.listar_alertas_completude")
def test_alertas_completude_nao_repete_a_chamada_http(mock_listar):
    mock_listar.return_value = {"items": []}

    data_cache.alertas_completude("token", status="ABERTO", page=1, page_size=10)
    data_cache.alertas_completude("token", status="ABERTO", page=1, page_size=10)
    data_cache.alertas_completude("token", status="ABERTO", page=1, page_size=10)

    assert mock_listar.call_count == 1, "o cache deve evitar refazer a mesma consulta"


def test_ttls_sao_coerentes_com_o_tipo_de_dado():
    """Cadastro muda pouco e pode viver mais; agregados derivam da view, que é
    reatualizada a cada escrita, então precisam expirar antes."""
    assert data_cache.TTL_AGREGADO < data_cache.TTL_CADASTRO
