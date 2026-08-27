"""RF19 - Botão "Exportar CSV" das telas de listagem."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

CSV = b"Data;Vacina\r\n15/01/2024;BCG\r\n"


def _resultado_vazio(page_size=5):
    return {"items": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 0}


def _abrir_registros():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "registros"
    return at


def _botao_exportar(at, key="registros"):
    return at.button(key=f"exportar_{key}")


def _download(at):
    return at.get("download_button")


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_download_so_aparece_depois_de_clicar_em_exportar(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()

    assert not at.exception
    assert _download(at) == []
    # A tela não pode buscar o arquivo antes do usuário pedir.
    mock_exportar.assert_not_called()

    at = _botao_exportar(at).click().run()

    assert not at.exception
    assert [d.label for d in _download(at)] == ["Baixar CSV"]
    mock_exportar.assert_called_once()


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_exportacao_de_registros_usa_os_filtros_da_tela(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = [("2304400", "Fortaleza")]
    mock_vacinas.return_value = []

    at = _abrir_registros()
    at.session_state["dados_municipios"] = [{"nome": "Fortaleza", "id_ibge": "2304400"}]
    at.session_state["filtro_mun"] = "Fortaleza (2304400)"
    at.session_state["reg_busca"] = "bcg"
    at = at.run()
    at = _botao_exportar(at).click().run()

    assert not at.exception
    args, kwargs = mock_exportar.call_args
    assert args[0] == "faketoken"
    assert args[1] == "registros"
    assert kwargs["municipio_id"] == "2304400"
    assert kwargs["search"] == "bcg"
    assert kwargs["data_inicio"] == "2024-01-01"


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_erro_da_api_vira_mensagem_e_nao_oferece_download(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    mock_exportar.side_effect = ApiError("O servidor demorou para responder.")
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    at = _botao_exportar(at).click().run()

    assert not at.exception
    assert any("O servidor demorou" in erro.value for erro in at.error)
    assert _download(at) == []


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_recorte_truncado_avisa_o_usuario_e_ainda_oferece_download(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    mock_exportar.return_value = (CSV, True)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    at = _botao_exportar(at).click().run()

    assert not at.exception
    assert any("refine os filtros" in aviso.value.lower() for aviso in at.warning)
    assert [d.label for d in _download(at)] == ["Baixar CSV"]


@patch("streamlit.download_button")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_arquivo_baixado_leva_o_conteudo_e_o_nome_do_recurso(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas, mock_download
):
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    _botao_exportar(at).click().run()

    kwargs = mock_download.call_args.kwargs
    assert kwargs["data"] == CSV
    assert kwargs["file_name"] == "registros.csv"
    assert kwargs["mime"] == "text/csv"


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_trocar_de_filtro_descarta_o_arquivo_ja_preparado(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    """Baixar um arquivo montado com o recorte anterior entregaria ao gestor
    dados diferentes dos que a tela está mostrando."""
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = [("2304400", "Fortaleza")]
    mock_vacinas.return_value = []

    at = _abrir_registros()
    at.session_state["dados_municipios"] = [{"nome": "Fortaleza", "id_ibge": "2304400"}]
    at = at.run()
    at = _botao_exportar(at).click().run()
    assert [d.label for d in _download(at)] == ["Baixar CSV"]

    # selectbox[3] é o filtro de município da listagem (0-2 são os do formulário).
    at.selectbox[3].select("Fortaleza (2304400)")
    at = at.run()

    assert not at.exception
    assert _download(at) == []


# ============================================================
# DEMAIS TELAS DE LISTAGEM
# ============================================================


def _abrir(pagina):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = pagina
    return at


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
@patch("exportacao_ui.exportar_csv")
def test_tela_de_cadastro_exporta_municipios_e_vacinas_separadamente(
    mock_exportar, mock_municipios, mock_vacinas
):
    mock_exportar.return_value = (CSV, False)
    mock_municipios.return_value = _resultado_vazio(page_size=3)
    mock_vacinas.return_value = _resultado_vazio(page_size=3)

    at = _abrir("municipios").run()
    assert not at.exception

    at = _botao_exportar(at, "municipios").click().run()
    assert mock_exportar.call_args.args[1] == "municipios"

    at = _botao_exportar(at, "vacinas").click().run()
    assert mock_exportar.call_args.args[1] == "vacinas"
    assert not at.exception


@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("fluxo_ui.fluxo_intermunicipal")
@patch("exportacao_ui.exportar_csv")
def test_tela_de_fluxo_exporta_com_os_filtros_do_recorte(
    mock_exportar, mock_fluxo, mock_municipios, mock_vacinas
):
    mock_exportar.return_value = (CSV, False)
    mock_fluxo.return_value = {
        "items": [],
        "total": 0,
        "total_doses": 0,
        "page": 1,
        "page_size": 25,
        "total_pages": 0,
    }
    mock_municipios.return_value = [("2304400", "Fortaleza")]
    mock_vacinas.return_value = [(1, "COVID-19")]

    at = _abrir("fluxo").run()
    at = _botao_exportar(at, "fluxo").click().run()

    assert not at.exception
    assert mock_exportar.call_args.args[1] == "fluxo"
    assert set(mock_exportar.call_args.kwargs) == {
        "vacina_id",
        "data_inicio",
        "data_fim",
        "municipio_id",
    }


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
@patch("exportacao_ui.exportar_csv")
def test_tela_de_completude_exporta_com_os_filtros_do_recorte(
    mock_exportar, mock_alertas, mock_municipios
):
    mock_exportar.return_value = (CSV, False)
    mock_municipios.return_value = [("2304400", "Fortaleza")]
    mock_alertas.return_value = {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "total_pages": 0,
        "totais_por_status": {
            "ABERTO": 0,
            "INVESTIGANDO": 0,
            "RESOLVIDO": 0,
            "FALSO_POSITIVO": 0,
        },
        "municipios_afetados": 0,
    }

    at = _abrir("completude").run()
    at = _botao_exportar(at, "completude").click().run()

    assert not at.exception
    assert mock_exportar.call_args.args[1] == "completude"
    assert set(mock_exportar.call_args.kwargs) == {"status", "municipio_id", "ano"}


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_tela_de_sazonalidade_nao_oferece_exportacao(
    mock_saz, mock_municipios, mock_vacinas
):
    """Sazonalidade é o único painel sem exportação: o gráfico dos doze meses
    é a leitura, não uma listagem que o gestor leve para fora."""
    mock_municipios.return_value = []
    mock_vacinas.return_value = []
    mock_saz.return_value = {
        "kpis": {
            "total_periodo": 0,
            "media_mensal": 0,
            "mes_pico": None,
            "mes_pico_nome": None,
            "mes_vale": None,
            "mes_vale_nome": None,
            "amplitude": 0.0,
        },
        "meses": [],
    }

    at = _abrir("sazonalidade").run()

    assert not at.exception
    assert [b for b in at.button if b.key == "exportar_sazonalidade"] == []


@patch("alta_complexidade_ui.alta_complexidade")
@patch("exportacao_ui.exportar_csv")
def test_tela_de_alta_complexidade_exporta_com_o_top_selecionado(
    mock_exportar, mock_painel
):
    mock_exportar.return_value = (CSV, False)
    mock_painel.return_value = {"items": [], "total_vacinas": 0}

    at = _abrir("alta_complexidade").run()
    at = _botao_exportar(at, "alta_complexidade").click().run()

    assert not at.exception
    assert mock_exportar.call_args.args[1] == "alta-complexidade"
    assert mock_exportar.call_args.kwargs == {"top_municipios": 3}


# ============================================================
# ESPERA E BLOQUEIO DO BOTÃO
# ============================================================


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_botao_exportar_fica_indisponivel_com_o_arquivo_ja_pronto(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    """Enquanto o arquivo do recorte atual está pronto para baixar, clicar de
    novo em Exportar só repetiria a mesma consulta pesada."""
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    assert _botao_exportar(at).disabled is False

    at = _botao_exportar(at).click().run()

    assert not at.exception
    assert _botao_exportar(at).disabled is True
    assert mock_exportar.call_count == 1


@patch("streamlit.spinner")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_preparo_do_arquivo_mostra_uma_espera(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas, mock_spinner
):
    mock_exportar.return_value = (CSV, False)
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    mock_spinner.reset_mock()
    _botao_exportar(at).click().run()

    mensagens = [chamada.args[0] for chamada in mock_spinner.call_args_list if chamada.args]
    assert any("Preparando" in mensagem for mensagem in mensagens)


@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
@patch("registros_ui.listar_registros")
@patch("exportacao_ui.exportar_csv")
def test_erro_na_exportacao_mantem_o_botao_disponivel_para_nova_tentativa(
    mock_exportar, mock_registros, mock_municipios, mock_vacinas
):
    mock_exportar.side_effect = ApiError("O servidor demorou para responder.")
    mock_registros.return_value = _resultado_vazio()
    mock_municipios.return_value = []
    mock_vacinas.return_value = []

    at = _abrir_registros().run()
    at = _botao_exportar(at).click().run()

    assert not at.exception
    assert _botao_exportar(at).disabled is False
