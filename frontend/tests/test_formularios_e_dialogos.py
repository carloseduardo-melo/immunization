"""Cobre os formulários (cadastro/edição), as ações de linha e os diálogos de
confirmação — os ramos que só rodam quando o usuário submete ou clica."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]
_VACINAS = [(1, "COVID-19")]


def _app(pagina, **estado):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = pagina
    for chave, valor in estado.items():
        at.session_state[chave] = valor
    return at


def _lista_municipios(ativo=True):
    return {
        "items": [{"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
                   "regiao_saude": "Região de Fortaleza", "polo": True, "ativo": ativo}],
        "total": 1, "page": 1, "page_size": 3, "total_pages": 1,
    }


def _lista_vacinas(ativo=True):
    return {
        "items": [{"id": 1, "nome": "COVID-19", "alta_complexidade": False, "ativo": ativo}],
        "total": 1, "page": 1, "page_size": 3, "total_pages": 1,
    }


def _registros():
    return {
        "items": [{"id": "uuid-1", "data_vacinacao": "2024-01-10",
                   "municipio_vacina_nome": "Fortaleza", "municipio_vacina_id": "2304400",
                   "vacina_nome": "COVID-19", "vacina_id": 1,
                   "status_dado": "VALIDO", "idade": 30, "quantidade": 1}],
        "total": 1, "page": 1, "page_size": 5, "total_pages": 1,
    }


def _clicar(at, rotulo):
    """Clica no primeiro botão com esse rótulo (ações da página)."""
    for botao in at.button:
        if botao.label == rotulo:
            return botao.click().run()
    raise AssertionError(f"botão {rotulo!r} não encontrado")


def _submeter(at, formulario):
    """Submete um formulário pela chave que o Streamlit dá ao botão."""
    return at.button(key=f"FormSubmitter:{formulario}-Salvar").click().run()


def _clicar_dialogo(at, rotulo):
    """Clica no botão do diálogo de confirmação.

    Os widgets do diálogo são renderizados por último e sem `key`, então
    procurar de trás para frente evita acertar o botão homônimo da linha da
    tabela (por exemplo o "Desativar" de cada município).
    """
    for botao in reversed(list(at.button)):
        if botao.label == rotulo and botao.key is None:
            return botao.click().run()
    raise AssertionError(f"botão {rotulo!r} do diálogo não encontrado")


# ============================================================
# FORMULÁRIO DE MUNICÍPIO
# ============================================================

@patch("municipios_ui.criar_municipio")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cadastrar_municipio_chama_a_api(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.text_input[0].set_value("Sobral")
    _clicar(at, "Salvar")

    assert not at.exception
    mock_criar.assert_called_once()
    payload = mock_criar.call_args.args[1]
    assert payload["nome"] == "Sobral"
    assert payload["uf"] == "CE"
    assert len(payload["id_ibge"]) == 7


@patch("municipios_ui.criar_municipio")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cadastrar_municipio_sem_nome_e_bloqueado(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.text_input[0].set_value("   ")
    _clicar(at, "Salvar")

    assert not at.exception
    assert any("nome do município" in e.value for e in at.error)
    mock_criar.assert_not_called()


@patch("municipios_ui.criar_municipio")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_erro_da_api_ao_cadastrar_municipio_e_exibido(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()
    mock_criar.side_effect = ApiError("IBGE já cadastrado.")

    at = _app("municipios")
    at.run()
    at.text_input[0].set_value("Sobral")
    _clicar(at, "Salvar")

    assert not at.exception
    assert any("IBGE já cadastrado." in e.value for e in at.error)


@patch("municipios_ui.atualizar_municipio")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_editar_municipio_chama_a_api_de_atualizacao(mock_lm, mock_lv, mock_atualizar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()
    editando = {"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
                "regiao_saude": "Região de Fortaleza", "polo": True, "ativo": True}

    at = _app("municipios", municipio_editando=editando)
    at.run()
    at.text_input[0].set_value("Fortaleza Editada")
    _clicar(at, "Salvar")

    assert not at.exception
    mock_atualizar.assert_called_once()
    assert mock_atualizar.call_args.args[1] == "2304400"
    assert mock_atualizar.call_args.args[2]["nome"] == "Fortaleza Editada"


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cancelar_edicao_de_municipio_limpa_o_estado(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()
    editando = {"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
                "regiao_saude": None, "polo": False, "ativo": True}

    at = _app("municipios", municipio_editando=editando)
    at.run()
    _clicar(at, "Cancelar")

    assert not at.exception
    assert at.session_state["municipio_editando"] is None


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_botao_editar_da_linha_carrega_o_municipio(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.button(key="editar_2304400").click().run()

    assert not at.exception
    assert at.session_state["municipio_editando"]["id_ibge"] == "2304400"


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_botao_desativar_da_linha_marca_confirmacao(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.button(key="desativar_2304400").click().run()

    assert not at.exception
    assert at.session_state["municipio_confirmando_id"] == "2304400"


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_paginacao_de_municipios(mock_lm, mock_lv):
    resultado = _lista_municipios()
    resultado.update({"total": 9, "total_pages": 3})
    mock_lm.return_value = resultado
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.button(key="next_mun").click().run()

    assert not at.exception
    assert at.session_state["municipios_page"] == 2


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_busca_de_municipio_reinicia_a_paginacao(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios", municipios_page=3)
    at.run()
    at.text_input(key="input_busca_mun").set_value("sobral").run()

    assert not at.exception
    assert at.session_state["municipios_busca"] == "sobral"
    assert at.session_state["municipios_page"] == 1


# ============================================================
# FORMULÁRIO DE VACINA
# ============================================================

@patch("municipios_ui.criar_vacina")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cadastrar_vacina_chama_a_api(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.text_input[2].set_value("BCG")
    _submeter(at, "form_vacina")

    assert not at.exception
    mock_criar.assert_called_once()
    assert mock_criar.call_args.args[1]["nome"] == "BCG"


@patch("municipios_ui.criar_vacina")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_cadastrar_vacina_sem_nome_e_bloqueado(mock_lm, mock_lv, mock_criar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.text_input[2].set_value("  ")
    _submeter(at, "form_vacina")

    assert not at.exception
    assert any("nome da vacina" in e.value for e in at.error)
    mock_criar.assert_not_called()


@patch("municipios_ui.atualizar_vacina")
@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_editar_vacina_chama_a_api(mock_lm, mock_lv, mock_atualizar):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios", vacina_editando={"id": 1, "nome": "COVID-19",
                                             "alta_complexidade": True, "ativo": True})
    at.run()
    at.text_input[2].set_value("COVID-19 bivalente")
    _submeter(at, "form_vacina")

    assert not at.exception
    mock_atualizar.assert_called_once()
    assert mock_atualizar.call_args.args[1] == 1


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_acoes_de_linha_da_vacina(mock_lm, mock_lv):
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = _lista_vacinas()

    at = _app("municipios")
    at.run()
    at.button(key="editar_vac_1").click().run()
    assert at.session_state["vacina_editando"]["id"] == 1

    at2 = _app("municipios")
    at2.run()
    at2.button(key="desativar_vac_1").click().run()
    assert at2.session_state["vacina_confirmando_id"] == 1
    assert not at2.exception


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_paginacao_e_busca_de_vacinas(mock_lm, mock_lv):
    resultado = _lista_vacinas()
    resultado.update({"total": 9, "total_pages": 3})
    mock_lm.return_value = _lista_municipios()
    mock_lv.return_value = resultado

    at = _app("municipios")
    at.run()
    at.button(key="next_vac").click().run()
    assert at.session_state["vacinas_page"] == 2

    at2 = _app("municipios", vacinas_page=3)
    at2.run()
    at2.text_input(key="input_busca_vac").set_value("bcg").run()
    assert at2.session_state["vacinas_busca"] == "bcg"
    assert at2.session_state["vacinas_page"] == 1
    assert not at2.exception


# ============================================================
# REGISTROS: formulário, ações de linha e diálogo
# ============================================================

@patch("registros_ui.criar_registro")
@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_cadastrar_registro_chama_a_api(mock_mun, mock_vac, mock_lista, mock_criar):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()

    at = _app("registros")
    at.run()
    at.selectbox[0].select("Fortaleza (2304400)")
    at.selectbox[1].select("COVID-19 (ID: 1)")
    _clicar(at, "Salvar")

    assert not at.exception
    mock_criar.assert_called_once()
    payload = mock_criar.call_args.args[1]
    assert payload["municipio_vacina_id"] == "2304400"
    assert payload["vacina_id"] == 1


@patch("registros_ui.criar_registro")
@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_cadastrar_registro_sem_selecao_e_bloqueado(mock_mun, mock_vac, mock_lista, mock_criar):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()

    at = _app("registros")
    at.run()
    _clicar(at, "Salvar")

    assert not at.exception
    assert any("Selecione o Município e a Vacina." in e.value for e in at.error)
    mock_criar.assert_not_called()


@patch("registros_ui.criar_registro")
@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_erro_da_api_ao_cadastrar_registro(mock_mun, mock_vac, mock_lista, mock_criar):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()
    mock_criar.side_effect = ApiError("Município não encontrado.")

    at = _app("registros")
    at.run()
    at.selectbox[0].select("Fortaleza (2304400)")
    at.selectbox[1].select("COVID-19 (ID: 1)")
    _clicar(at, "Salvar")

    assert not at.exception
    assert any("Município não encontrado." in e.value for e in at.error)


@patch("registros_ui.atualizar_registro")
@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_editar_registro_chama_a_api(mock_mun, mock_vac, mock_lista, mock_atualizar):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()
    editando = _registros()["items"][0]

    at = _app("registros", registro_editando=editando)
    at.run()
    _clicar(at, "Salvar")

    assert not at.exception
    mock_atualizar.assert_called_once()
    assert mock_atualizar.call_args.args[1] == "uuid-1"


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_cancelar_edicao_de_registro(mock_mun, mock_vac, mock_lista):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()

    at = _app("registros", registro_editando=_registros()["items"][0])
    at.run()
    _clicar(at, "Cancelar")

    assert not at.exception
    assert at.session_state["registro_editando"] is None


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_acoes_de_linha_do_registro(mock_mun, mock_vac, mock_lista):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()

    at = _app("registros")
    at.run()
    at.button(key="ed_uuid-1").click().run()
    assert at.session_state["registro_editando"]["id"] == "uuid-1"

    at2 = _app("registros")
    at2.run()
    at2.button(key="del_uuid-1").click().run()
    assert at2.session_state["registro_confirmando_id"] == "uuid-1"
    assert not at2.exception


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_busca_de_registro_reinicia_paginacao(mock_mun, mock_vac, mock_lista):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_lista.return_value = _registros()

    at = _app("registros", reg_page=4)
    at.run()
    at.text_input[0].set_value("fortaleza").run()

    assert not at.exception
    assert at.session_state["reg_busca"] == "fortaleza"
    assert at.session_state["reg_page"] == 1


# ============================================================
# FLUXO: paginação da tabela
# ============================================================

@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_paginacao_da_tabela_de_fluxo(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = {
        "items": [{"municipio_origem_id": "2303709", "municipio_origem_nome": "Caucaia",
                   "municipio_destino_id": "2304400", "municipio_destino_nome": "Fortaleza",
                   "total_doses": 7}],
        "total": 100, "page": 1, "page_size": 25, "total_pages": 4, "total_doses": 700,
    }

    at = _app("fluxo")
    at.run()
    at.button(key="fluxo_next").click().run()
    assert at.session_state["fluxo_page"] == 2

    at2 = _app("fluxo", fluxo_page=3)
    at2.run()
    at2.button(key="fluxo_prev").click().run()
    assert at2.session_state["fluxo_page"] == 2
    assert not at2.exception


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_erro_de_api_na_pagina_da_tabela_de_fluxo(mock_mun, mock_vac, mock_fluxo):
    """A 1ª chamada (heatmap) funciona e a 2ª (tabela) falha."""
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    ok = {
        "items": [{"municipio_origem_id": "2303709", "municipio_origem_nome": "Caucaia",
                   "municipio_destino_id": "2304400", "municipio_destino_nome": "Fortaleza",
                   "total_doses": 7}],
        "total": 1, "page": 1, "page_size": 15, "total_pages": 1, "total_doses": 7,
    }
    mock_fluxo.side_effect = [ok, ApiError("Falha ao paginar.")]

    at = _app("fluxo")
    at.run()

    assert not at.exception
    assert any("Falha ao paginar." in e.value for e in at.error)


# ============================================================
# CONFIRMAÇÕES DE DESATIVAÇÃO
# ============================================================
# O diálogo em si não é exercitável pelo AppTest: a tela marca
# `*_dialog_shown = True` antes de abri-lo, então no rerun disparado pelo
# clique ele não é reconstruído. A regra que importa foi extraída para as
# funções abaixo, testadas diretamente.

@patch("municipios_ui.desativar_municipio")
def test_confirmar_desativacao_municipio_sucesso(mock_desativar):
    import streamlit as st

    import municipios_ui

    st.session_state.clear()
    st.session_state["municipio_confirmando_id"] = "2304400"

    municipios_ui.confirmar_desativacao("token", "2304400")

    mock_desativar.assert_called_once_with("token", "2304400")
    assert st.session_state["municipio_confirmando_id"] is None


@patch("municipios_ui.desativar_vacina")
def test_confirmar_desativacao_vacina_sucesso(mock_desativar):
    import streamlit as st

    import municipios_ui

    st.session_state.clear()
    st.session_state["vacina_confirmando_id"] = 1

    municipios_ui.confirmar_desativacao_vacina("token", 1)

    mock_desativar.assert_called_once_with("token", 1)
    assert st.session_state["vacina_confirmando_id"] is None


@patch("municipios_ui.desativar_vacina")
def test_confirmar_desativacao_vacina_com_erro_mantem_estado(mock_desativar):
    import streamlit as st

    import municipios_ui

    mock_desativar.side_effect = ApiError("Não foi possível desativar.")
    st.session_state.clear()
    st.session_state["vacina_confirmando_id"] = 1

    municipios_ui.confirmar_desativacao_vacina("token", 1)

    assert st.session_state["vacina_confirmando_id"] == 1


@patch("registros_ui.desativar_registro")
def test_confirmar_desativacao_registro_sucesso(mock_desativar):
    import streamlit as st

    import registros_ui

    st.session_state.clear()
    st.session_state["registro_confirmando_id"] = "uuid-1"

    registros_ui.confirmar_desativacao_registro("token", "uuid-1")

    mock_desativar.assert_called_once_with("token", "uuid-1")
    assert st.session_state["registro_confirmando_id"] is None


@patch("registros_ui.desativar_registro")
def test_confirmar_desativacao_registro_com_erro_mantem_estado(mock_desativar):
    import streamlit as st

    import registros_ui

    mock_desativar.side_effect = ApiError("Registro já inativo.")
    st.session_state.clear()
    st.session_state["registro_confirmando_id"] = "uuid-1"

    registros_ui.confirmar_desativacao_registro("token", "uuid-1")

    assert st.session_state["registro_confirmando_id"] == "uuid-1"
