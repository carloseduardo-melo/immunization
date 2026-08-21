"""RF18 - Tela de imunobiológicos de alta complexidade."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError
from theme import BADGE_TONES


def _payload():
    """Quatro vacinas cobrindo os três tons de badge e o caso sem registro."""
    return {
        "items": [
            {
                "vacina_id": 1,
                "vacina_nome": "Imunoglobulina",
                "total_doses": 200,
                "total_deslocamentos": 130,
                "taxa_deslocamento": 65.0,
                "centro_referencia_id": "2304400",
                "centro_referencia_nome": "Fortaleza",
                "municipios": [
                    {"municipio_id": "2304400", "municipio_nome": "Fortaleza",
                     "total_doses": 150, "percentual": 75.0},
                    {"municipio_id": "2312908", "municipio_nome": "Sobral",
                     "total_doses": 30, "percentual": 15.0},
                    {"municipio_id": "2303709", "municipio_nome": "Caucaia",
                     "total_doses": 20, "percentual": 10.0},
                ],
            },
            {
                "vacina_id": 2,
                "vacina_nome": "Raiva humana",
                "total_doses": 100,
                "total_deslocamentos": 30,
                "taxa_deslocamento": 30.0,
                "centro_referencia_id": "2312908",
                "centro_referencia_nome": "Sobral",
                "municipios": [
                    {"municipio_id": "2312908", "municipio_nome": "Sobral",
                     "total_doses": 100, "percentual": 100.0},
                ],
            },
            {
                "vacina_id": 3,
                "vacina_nome": "Palivizumabe",
                "total_doses": 40,
                "total_deslocamentos": 4,
                "taxa_deslocamento": 10.0,
                "centro_referencia_id": "2304400",
                "centro_referencia_nome": "Fortaleza",
                "municipios": [
                    {"municipio_id": "2304400", "municipio_nome": "Fortaleza",
                     "total_doses": 40, "percentual": 100.0},
                ],
            },
            {
                "vacina_id": 4,
                "vacina_nome": "Soro antirrábico",
                "total_doses": 0,
                "total_deslocamentos": 0,
                "taxa_deslocamento": 0.0,
                "centro_referencia_id": None,
                "centro_referencia_nome": None,
                "municipios": [],
            },
        ],
        "total_vacinas": 4,
    }


def _abrir():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "alta_complexidade"
    return at


@patch("alta_complexidade_ui.alta_complexidade")
def test_tela_lista_as_vacinas_e_os_centros(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Alta Complexidade" in textos
    assert "Imunoglobulina" in textos
    assert "Fortaleza" in textos
    assert "65.0%" in textos
    assert "—" in textos, "vacina sem registro não tem centro de referência"


def _badge_com_rotulo(markdowns, rotulo):
    """Devolve o valor markdown do único badge cujo rótulo é o percentual dado.

    Filtra por "background:" para não confundir com o percentual simples de
    município no ranking (que não é um badge - não tem esse estilo inline).
    """
    candidatos = [
        m.value
        for m in markdowns
        if m.value and rotulo in m.value and "background:" in m.value
    ]
    assert len(candidatos) == 1, f"esperava um único badge com rótulo {rotulo!r}"
    return candidatos[0]


@patch("alta_complexidade_ui.alta_complexidade")
def test_tom_do_badge_reflete_a_taxa_de_deslocamento(mock_dados):
    """Amarra o tom renderizado à cor real de theme.BADGE_TONES, por vacina -
    não só à presença do texto do percentual - para pegar limiares trocados ou
    um tom fixo que passaria despercebido apenas conferindo a cobertura."""
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    _, cor_danger = BADGE_TONES["danger"]
    _, cor_warning = BADGE_TONES["warning"]
    _, cor_neutral = BADGE_TONES["neutral"]

    badge_65 = _badge_com_rotulo(at.markdown, "65.0%")
    badge_30 = _badge_com_rotulo(at.markdown, "30.0%")
    badge_10 = _badge_com_rotulo(at.markdown, "10.0%")

    assert cor_danger in badge_65, "Imunoglobulina (65%) deveria usar o tom danger"
    assert cor_warning in badge_30, "Raiva humana (30%) deveria usar o tom warning"
    assert cor_neutral in badge_10, "Palivizumabe (10%) deveria usar o tom neutral"


@patch("alta_complexidade_ui.alta_complexidade")
def test_tela_mostra_os_kpis_ponderados(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Vacinas de alta complexidade"] == "4"
    assert valores["Doses aplicadas"] == "340"
    assert valores["Taxa geral de deslocamento"] == "48.24%", "164 / 340"


@patch("alta_complexidade_ui.alta_complexidade")
def test_cada_vacina_tem_o_ranking_de_municipios(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Sobral (2312908)" in textos
    assert "Caucaia (2303709)" in textos
    assert any("Nenhuma dose registrada" in (c.value or "") for c in at.caption)


@patch("alta_complexidade_ui.alta_complexidade")
def test_seletor_de_top_municipios_e_repassado(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()
    at.selectbox(key="alta_top_municipios").select(10).run()

    assert not at.exception
    assert mock_dados.call_args.kwargs["top_municipios"] == 10


@patch("alta_complexidade_ui.alta_complexidade")
def test_taxa_geral_com_zero_doses_nao_divide_por_zero(mock_dados):
    dados = _payload()
    dados["items"] = [dados["items"][-1]]
    dados["total_vacinas"] = 1
    mock_dados.return_value = dados

    at = _abrir().run()

    assert not at.exception
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Taxa geral de deslocamento"] == "0.0%"


@patch("alta_complexidade_ui.alta_complexidade")
def test_sem_vacinas_de_alta_complexidade_mostra_aviso(mock_dados):
    mock_dados.return_value = {"items": [], "total_vacinas": 0}

    at = _abrir().run()

    assert not at.exception
    assert any("Nenhuma vacina" in (i.value or "") for i in at.info)
    assert len(at.metric) == 0


@patch("alta_complexidade_ui.alta_complexidade")
def test_erro_da_api_exibe_mensagem(mock_dados):
    mock_dados.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("alta_complexidade_ui.alta_complexidade")
@patch("alta_complexidade_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_dados):
    import streamlit as st

    import alta_complexidade_ui

    st.session_state.clear()
    alta_complexidade_ui.render_alta_complexidade_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para visualizar este painel."
    )
    mock_dados.assert_not_called()
