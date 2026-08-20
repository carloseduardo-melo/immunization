from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]


def _pagina_alertas(status="ABERTO"):
    return {
        "items": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "referencia_ano": 2024,
                "referencia_mes": 9,
                "municipio_id": "2304400",
                "municipio_nome": "Fortaleza",
                "total_observado": 10,
                "status": status,
                "criado_em": "2026-08-20T10:00:00",
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 10,
        "total_pages": 1,
        "totais_por_status": {
            "ABERTO": 1,
            "INVESTIGANDO": 0,
            "RESOLVIDO": 0,
            "FALSO_POSITIVO": 0,
        },
        "municipios_afetados": 1,
    }


def _abrir(role="ADMIN", municipio_id=None):
    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = role
    at.session_state["municipio_id"] = municipio_id
    at.session_state["pagina_ativa"] = "completude"
    return at


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_tela_lista_os_alertas(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert mock_alertas.called
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Alertas de Completude" in textos
    assert "Fortaleza" in textos
    assert "09/2024" in textos


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_tela_mostra_os_kpis(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Total de alertas"] == "1"
    assert valores["Abertos"] == "1"
    assert valores["Em investigação"] == "0"
    assert valores["Municípios afetados"] == "1"


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_filtro_de_status_e_repassado_a_api(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas("RESOLVIDO")
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.selectbox(key="completude_status").select("Resolvido").run()

    assert not at.exception
    assert mock_alertas.call_args.kwargs["status"] == "RESOLVIDO"


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_filtro_de_municipio_e_ano_sao_repassados(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.selectbox(key="completude_municipio").select("Fortaleza (2304400)").run()
    at.number_input(key="completude_ano").set_value(2024).run()

    assert not at.exception
    assert mock_alertas.call_args.kwargs["municipio_id"] == "2304400"
    assert mock_alertas.call_args.kwargs["ano"] == 2024


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_trocar_filtro_reseta_a_pagina_para_1(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.session_state["completude_page"] = 3

    at.selectbox(key="completude_status").select("Resolvido").run()

    assert not at.exception
    assert mock_alertas.call_args.kwargs["page"] == 1


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_lista_vazia_mostra_aviso(mock_alertas, mock_municipios):
    vazio = _pagina_alertas()
    vazio["items"] = []
    vazio["total"] = 0
    vazio["total_pages"] = 0
    vazio["municipios_afetados"] = 0
    vazio["totais_por_status"] = {
        "ABERTO": 0,
        "INVESTIGANDO": 0,
        "RESOLVIDO": 0,
        "FALSO_POSITIVO": 0,
    }
    mock_alertas.return_value = vazio
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Nenhum alerta" in (i.value or "") for i in at.info)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_da_api_exibe_mensagem(mock_alertas, mock_municipios):
    mock_alertas.side_effect = ApiError("Servidor indisponível.")
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_ao_carregar_municipios_nao_quebra_a_tela(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert mock_alertas.called


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_gestor_municipal_nao_ve_acoes_de_admin(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir(role="GESTOR_MUNICIPAL", municipio_id="2304400").run()

    assert not at.exception
    chaves = [b.key for b in at.button]
    assert "completude_varredura" not in chaves


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_paginacao_avanca_e_volta(mock_alertas, mock_municipios):
    # Duas instâncias de AppTest (uma por sentido), como já é feito em
    # test_formularios_e_dialogos.py e test_ramos_restantes.py: clicar duas
    # vezes seguidas na MESMA instância de AppTest não é confiável neste
    # app — o componente CookieController (instanciado em todo carregamento
    # de app.py) interfere no registro do clique do botão a cada segunda
    # chamada de .run() sobre a mesma instância.
    pagina = _pagina_alertas()
    pagina["total"] = 25
    pagina["total_pages"] = 3
    mock_alertas.return_value = pagina
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.button(key="completude_proxima").click().run()
    assert mock_alertas.call_args.kwargs["page"] == 2

    at2 = _abrir()
    at2.session_state["completude_page"] = 2
    at2.run()
    at2.button(key="completude_anterior").click().run()
    assert mock_alertas.call_args.kwargs["page"] == 1


@patch("completude_ui.alertas_completude")
@patch("completude_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_alertas):
    import streamlit as st

    import completude_ui

    st.session_state.clear()
    completude_ui.render_completude_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para visualizar os alertas."
    )
    mock_alertas.assert_not_called()


@patch("completude_ui.recalcular_completude")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_admin_dispara_a_varredura(mock_alertas, mock_municipios, mock_recalcular):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_recalcular.return_value = {
        "alertas_criados": 2,
        "alertas_atualizados": 1,
        "municipios_analisados": 5,
        "meses_analisados": 60,
    }

    at = _abrir().run()
    at.button(key="completude_varredura").click().run()

    assert not at.exception
    assert mock_recalcular.called
    mensagem_esperada = (
        "Varredura concluída: 2 alerta(s) criado(s) e 1 atualizado(s) em 5 município(s)."
    )
    assert any(mensagem_esperada in (s.value or "") for s in at.success)


@patch("completude_ui.recalcular_completude")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_na_varredura_exibe_mensagem(mock_alertas, mock_municipios, mock_recalcular):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_recalcular.side_effect = ApiError("Operação não permitida para o seu perfil de acesso.")

    at = _abrir().run()
    at.button(key="completude_varredura").click().run()

    assert not at.exception
    assert any("não permitida" in (e.value or "") for e in at.error)


@patch("completude_ui.atualizar_status_alerta")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_admin_altera_o_status_de_um_alerta(mock_alertas, mock_municipios, mock_atualizar):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_atualizar.return_value = {"status": "INVESTIGANDO"}
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir().run()
    at.selectbox(key=f"completude_status_{alerta_id}").select("Investigando").run()
    at.button(key=f"completude_salvar_{alerta_id}").click().run()

    assert not at.exception
    assert mock_atualizar.call_args.args[1] == alerta_id
    assert mock_atualizar.call_args.args[2] == "INVESTIGANDO"


@patch("completude_ui.atualizar_status_alerta")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_ao_salvar_status_exibe_mensagem(mock_alertas, mock_municipios, mock_atualizar):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_atualizar.side_effect = ApiError("Alerta de completude não encontrado.")
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir().run()
    at.button(key=f"completude_salvar_{alerta_id}").click().run()

    assert not at.exception
    assert any("não encontrado" in (e.value or "") for e in at.error)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_gestor_estadual_ve_a_lista_sem_seletor_de_status(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir(role="GESTOR_ESTADUAL").run()

    assert not at.exception
    chaves = [s.key for s in at.selectbox]
    assert f"completude_status_{alerta_id}" not in chaves
