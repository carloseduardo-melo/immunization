"""RF17 - Tela de sazonalidade."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]
_VACINAS = [(1, "COVID-19"), (2, "Influenza")]

_NOMES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
          "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _payload(totais=None):
    """Por padrão: 10, 20, ... 120 doses. Média 65, pico Dez, vale Jan."""
    totais = totais if totais is not None else [mes * 10 for mes in range(1, 13)]
    total_periodo = sum(totais)
    media = total_periodo / 12
    meses = [
        {
            "mes": numero,
            "nome_mes": _NOMES[numero - 1],
            "total_doses": totais[numero - 1],
            "indice_sazonalidade": round(totais[numero - 1] / media, 2) if media else 0.0,
        }
        for numero in range(1, 13)
    ]
    return {
        "kpis": {
            "total_periodo": total_periodo,
            "media_mensal": round(media, 2),
            "mes_pico": 12,
            "mes_pico_nome": "Dez",
            "mes_vale": 1,
            "mes_vale_nome": "Jan",
            "amplitude": 12.0,
        },
        "meses": meses,
    }


def _vazio():
    dados = _payload(totais=[0] * 12)
    dados["kpis"].update(
        {"mes_pico": None, "mes_pico_nome": None, "mes_vale": None,
         "mes_vale_nome": None, "amplitude": 0.0}
    )
    return dados


def _abrir():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "sazonalidade"
    return at


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_tela_mostra_titulo_kpis_e_tabela(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Sazonalidade" in textos
    assert "Dez" in textos
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Mês de pico"] == "Dez"
    assert valores["Mês de vale"] == "Jan"
    assert valores["Amplitude"] == "12.0x"
    assert valores["Total do período"] == "780"


@patch("sazonalidade_ui.st.bar_chart")
@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_grafico_recebe_os_doze_meses_em_ordem(
    mock_saz, mock_municipios, mock_vacinas, mock_chart
):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    dados = mock_chart.call_args.args[0]
    assert list(dados.index) == [
        f"{numero:02d} {nome}" for numero, nome in zip(range(1, 13), _NOMES)
    ], "o prefixo numérico é o que mantém o eixo em ordem cronológica"
    assert list(dados["Doses"]) == [mes * 10 for mes in range(1, 13)]


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtros_sao_repassados_a_api(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_vacina").select("Influenza (ID: 2)").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["vacina_id"] == 2


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtro_de_municipio_e_repassado(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_municipio").select("Fortaleza (2304400)").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["municipio_id"] == "2304400"


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtros_de_ano_sao_repassados(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_ano_inicio").select("2023").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["ano_inicio"] == 2023
    assert mock_saz.call_args.kwargs["ano_fim"] is None


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_ano_fim_e_repassado(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_ano_fim").select("2024").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["ano_fim"] == 2024


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_periodo_sem_dado_mostra_aviso(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _vazio()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    assert any("Não há registros" in (i.value or "") for i in at.info)
    assert len(at.metric) == 0


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_erro_da_api_exibe_mensagem(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.side_effect = ApiError("Servidor indisponível.")
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_listas_de_apoio_indisponiveis_nao_quebram_a_tela(
    mock_saz, mock_municipios, mock_vacinas
):
    mock_saz.return_value = _payload()
    mock_municipios.side_effect = ApiError("Servidor indisponível.")
    mock_vacinas.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert mock_saz.called


@patch("sazonalidade_ui.sazonalidade")
@patch("sazonalidade_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_saz):
    import streamlit as st

    import sazonalidade_ui

    st.session_state.clear()
    sazonalidade_ui.render_sazonalidade_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para visualizar a sazonalidade."
    )
    mock_saz.assert_not_called()
