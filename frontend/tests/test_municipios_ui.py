from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def _resultado_com_dados():
    return {
        "items": [
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
        ],
        "total": 1,
        "page": 1,
        "page_size": 10,
        "total_pages": 1,
    }


def _resultado_vazio():
    return {"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}


@patch("municipios_ui.listar_municipios")
def test_lista_municipios_carrega_e_exibe_dados(mock_listar):
    mock_listar.return_value = _resultado_com_dados()

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.run()

    assert not at.exception
    assert any("Fortaleza" in md.value for md in at.markdown)


@patch("municipios_ui.listar_municipios")
def test_lista_municipios_estado_vazio(mock_listar):
    mock_listar.return_value = _resultado_vazio()

    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "GESTOR_MUNICIPAL"
    at.session_state["municipio_id"] = "2304400"
    at.run()

    assert not at.exception
    assert any("Nenhum município encontrado" in info.value for info in at.info)
