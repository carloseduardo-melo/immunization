"""Cobre os ramos das telas que os testes de caminho feliz não alcançam:
erros de API, estados vazios, login, navegação e os diálogos de confirmação."""

from unittest.mock import patch

import pytest
import streamlit as st
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


def _resumo():
    return {
        "kpis": {
            "total_doses": 10,
            "total_deslocamentos": 2,
            "taxa_mobilidade": 20.0,
            "total_inconsistentes": 0,
        },
        "grafico": [{"mes": "2024-01", "deslocou": True, "total": 2}],
    }


def _pagina_fluxo(itens=None):
    return {
        "items": itens
        if itens is not None
        else [
            {
                "municipio_origem_id": "2303709",
                "municipio_origem_nome": "Caucaia",
                "municipio_destino_id": "2304400",
                "municipio_destino_nome": "Fortaleza",
                "total_doses": 7,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 25,
        "total_pages": 1,
        "total_doses": 7,
    }


# ============================================================
# TELA DE LOGIN (roda sem token)
# ============================================================

def test_tela_de_login_aparece_sem_token():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()

    assert not at.exception
    assert any("Entrar na sua conta" in md.value for md in at.markdown)


@patch("requests.post")
def test_login_com_campos_vazios_mostra_erro(mock_post):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()

    at.button[0].click().run()

    assert not at.exception
    assert any("Informe o e-mail e a senha" in e.value for e in at.error)
    mock_post.assert_not_called()


@patch("requests.post")
def test_login_com_credenciais_invalidas_mostra_erro(mock_post):
    mock_post.return_value.status_code = 401

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()
    at.text_input[0].set_value("a@b.c")
    at.text_input[1].set_value("errada")
    at.button[0].click().run()

    assert not at.exception
    assert any("incorretos" in e.value for e in at.error)


@patch("requests.post")
def test_login_com_falha_de_conexao_mostra_erro(mock_post):
    import requests as _rq

    mock_post.side_effect = _rq.exceptions.ConnectionError()

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = None
    at.run()
    at.text_input[0].set_value("a@b.c")
    at.text_input[1].set_value("senha")
    at.button[0].click().run()

    assert not at.exception
    assert any("conectar" in e.value for e in at.error)


# ============================================================
# NAVEGAÇÃO E PERFIL
# ============================================================

@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_gestor_municipal_ve_aviso_de_escopo(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "GESTOR_MUNICIPAL"
    at.session_state["municipio_id"] = "2304400"
    at.session_state["pagina_ativa"] = "registros"
    at.run()

    assert not at.exception
    assert any("2304400" in info.value for info in at.info)


@patch("streamlit_cookies_controller.CookieController")
@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_logout_limpa_a_sessao(mock_mun, mock_vac, mock_reg, mock_cookies):
    """O componente de cookies roda num iframe do navegador e não funciona no
    AppTest, então aqui ele é substituído por um dublê."""
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}
    mock_cookies.return_value.get.return_value = None

    at = _app("registros")
    at.run()
    at.sidebar.button(key="btn_logout").click().run()

    assert not at.exception
    assert at.session_state["token"] is None
    assert at.session_state["role"] is None
    assert at.session_state["_cookie_sync"] is None, "o pedido de limpeza do cookie deve ser consumido"


# ============================================================
# FLUXO INTERMUNICIPAL - ramos de erro e vazio
# ============================================================

@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_sem_dados_mostra_aviso(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _pagina_fluxo(itens=[])

    at = _app("fluxo")
    at.run()

    assert not at.exception
    assert any("Não há deslocamentos" in info.value for info in at.info)


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_com_erro_de_api_mostra_mensagem(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.side_effect = ApiError("Servidor indisponível.")

    at = _app("fluxo")
    at.run()

    assert not at.exception
    assert any("Servidor indisponível." in e.value for e in at.error)


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_lida_com_listas_de_apoio_indisponiveis(mock_mun, mock_vac, mock_fluxo):
    """Se a API de cadastro falhar, a tela ainda deve abrir (sem opções)."""
    mock_mun.side_effect = ApiError("fora do ar")
    mock_vac.side_effect = ApiError("fora do ar")
    mock_fluxo.return_value = _pagina_fluxo()

    at = _app("fluxo")
    at.run()

    assert not at.exception


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_filtro_de_municipio_e_repassado_a_api(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _pagina_fluxo()

    at = _app("fluxo")
    at.run()
    at.selectbox(key="fluxo_municipio").select("Fortaleza (2304400)").run()

    assert not at.exception
    assert any(
        c.kwargs.get("municipio_id") == "2304400" for c in mock_fluxo.call_args_list
    ), "o filtro de município precisa ir para a API, não ser aplicado no cliente"


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_filtro_de_vacina_e_repassado_a_api(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _pagina_fluxo()

    at = _app("fluxo")
    at.run()
    at.selectbox(key="fluxo_vacina").select("COVID-19 (ID: 1)").run()

    assert not at.exception
    assert any(c.kwargs.get("vacina_id") == 1 for c in mock_fluxo.call_args_list)


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_trocar_top_n_refaz_a_consulta(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _pagina_fluxo()

    at = _app("fluxo")
    at.run()
    at.selectbox(key="fluxo_sel_top_n").select(25).run()

    assert not at.exception
    assert at.session_state["fluxo_top_n"] == 25
    assert any(c.kwargs.get("page_size") == 25 for c in mock_fluxo.call_args_list)


@patch("fluxo_ui.fluxo_intermunicipal")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
def test_fluxo_trocar_tamanho_da_pagina_volta_para_a_primeira(mock_mun, mock_vac, mock_fluxo):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_fluxo.return_value = _pagina_fluxo()

    at = _app("fluxo", fluxo_page=5)
    at.run()
    at.selectbox(key="fluxo_sel_page_size").select(100).run()

    assert not at.exception
    assert at.session_state["fluxo_page_size"] == 100
    assert at.session_state["fluxo_page"] == 1, "trocar o tamanho deve voltar à página 1"


def test_fluxo_sem_token_avisa_e_nao_consulta():
    import fluxo_ui

    st.session_state.clear()
    fluxo_ui.render_fluxo_intermunicipal_section()
    fluxo_ui.render_fluxo_ranking_section()


def test_heatmap_recusa_matriz_acima_do_teto():
    """A rede de proteção precisa barrar a matriz antes de gerar o HTML."""
    import pandas as pd

    import fluxo_ui

    lado = 60  # 3.600 células > MAX_CELULAS_HEATMAP
    df = pd.DataFrame(
        [[1] * lado for _ in range(lado)],
        index=[f"O{i}" for i in range(lado)],
        columns=[f"D{i}" for i in range(lado)],
    )
    assert df.size > fluxo_ui.MAX_CELULAS_HEATMAP

    st.session_state.clear()
    fluxo_ui._renderizar_mapa_calor(df)


def test_heatmap_com_pivot_vazio_nao_quebra():
    import pandas as pd

    import fluxo_ui

    st.session_state.clear()
    fluxo_ui._renderizar_mapa_calor(pd.DataFrame())


# ============================================================
# RANKING - ramos de erro e vazio
# ============================================================

@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_ranking_vazio_mostra_aviso(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("Não há deslocamentos" in info.value for info in at.info)


@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_ranking_com_erro_de_api(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.side_effect = ApiError("Ranking indisponível.")

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("Ranking indisponível." in e.value for e in at.error)


def test_tabela_ranking_marca_saldo_positivo_negativo_e_zero():
    import fluxo_ui

    html = fluxo_ui._tabela_ranking(
        [
            {"municipio_nome": "Polo", "total_recebido": 10, "total_perdido": 2, "saldo_liquido": 8},
            {"municipio_nome": "Evasao", "total_recebido": 1, "total_perdido": 9, "saldo_liquido": -8},
            {"municipio_nome": "Neutro", "total_recebido": 5, "total_perdido": 5, "saldo_liquido": 0},
        ]
    )

    assert "+8" in html and "-8" in html
    assert "Polo" in html and "Evasao" in html and "Neutro" in html


# ============================================================
# DASHBOARD - ramos de erro e vazio
# ============================================================

@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_dashboard_com_erro_de_api(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.side_effect = ApiError("Dashboard fora do ar.")
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("Dashboard fora do ar." in e.value for e in at.error)


@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_dashboard_sem_serie_temporal_mostra_aviso(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = {"kpis": {}, "grafico": []}
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    at = _app("dashboard")
    at.run()

    assert not at.exception
    assert any("gerar o gráfico" in info.value for info in at.info)


@patch("fluxo_ui.ranking_fluxo")
@patch("fluxo_ui.listar_vacinas_resumido")
@patch("fluxo_ui.listar_municipios_resumido")
@patch("ui_dashboard.resumo_dashboard")
@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_dashboard_filtros_vao_para_a_api(
    mock_mun_d, mock_vac_d, mock_resumo, mock_mun_f, mock_vac_f, mock_ranking
):
    mock_mun_d.return_value = _MUNICIPIOS
    mock_vac_d.return_value = _VACINAS
    mock_resumo.return_value = _resumo()
    mock_mun_f.return_value = _MUNICIPIOS
    mock_vac_f.return_value = _VACINAS
    mock_ranking.return_value = {"top_polo": [], "top_evasao": []}

    at = _app("dashboard")
    at.run()
    at.selectbox[0].select("Fortaleza (2304400)").run()

    assert not at.exception
    assert any(c.kwargs.get("municipio_id") == "2304400" for c in mock_resumo.call_args_list)


@patch("ui_dashboard.listar_vacinas_resumido")
@patch("ui_dashboard.listar_municipios_resumido")
def test_dashboard_lida_com_listas_de_apoio_indisponiveis(mock_mun, mock_vac):
    import ui_dashboard

    mock_mun.side_effect = ApiError("fora do ar")
    mock_vac.side_effect = ApiError("fora do ar")

    assert ui_dashboard._carregar_dados_apoio("token") == ([], [])


def test_dashboard_sem_token_avisa():
    import ui_dashboard

    st.session_state.clear()
    ui_dashboard.render_dashboard_section()


# ============================================================
# MUNICÍPIOS E VACINAS
# ============================================================

@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_municipios_erro_de_api_mostra_mensagem(mock_mun, mock_vac):
    mock_mun.side_effect = ApiError("Falha ao listar municípios.")
    mock_vac.return_value = {"items": [], "total": 0, "page": 1, "page_size": 3, "total_pages": 0}

    at = _app("municipios")
    at.run()

    assert not at.exception
    assert any("Falha ao listar municípios." in e.value for e in at.error)


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_vacinas_lista_vazia_e_erro(mock_mun, mock_vac):
    mock_mun.return_value = {
        "items": [], "total": 0, "page": 1, "page_size": 3, "total_pages": 0
    }
    mock_vac.side_effect = ApiError("Falha ao listar vacinas.")

    at = _app("municipios")
    at.run()

    assert not at.exception
    assert any("Falha ao listar vacinas." in e.value for e in at.error)


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_municipios_e_vacinas_renderizam_listas(mock_mun, mock_vac):
    mock_mun.return_value = {
        "items": [
            {"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
             "regiao_saude": "Região de Fortaleza", "polo": True, "ativo": True},
            {"id_ibge": "2303709", "nome": "Caucaia", "uf": "CE",
             "regiao_saude": None, "polo": False, "ativo": False},
        ],
        "total": 2, "page": 1, "page_size": 3, "total_pages": 1,
    }
    mock_vac.return_value = {
        "items": [
            {"id": 1, "nome": "COVID-19", "alta_complexidade": True, "ativo": True},
            {"id": 2, "nome": "BCG", "alta_complexidade": False, "ativo": False},
        ],
        "total": 2, "page": 1, "page_size": 3, "total_pages": 1,
    }

    at = _app("municipios")
    at.run()

    assert not at.exception
    texto = " ".join(md.value for md in at.markdown)
    assert "Fortaleza" in texto and "Caucaia" in texto
    assert "COVID-19" in texto and "BCG" in texto
    assert "Inativo" in texto, "municípios/vacinas inativos precisam do selo"


@patch("municipios_ui.listar_vacinas")
@patch("municipios_ui.listar_municipios")
def test_gestor_municipal_nao_ve_acoes_de_edicao(mock_mun, mock_vac):
    mock_mun.return_value = {
        "items": [{"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE",
                   "regiao_saude": None, "polo": False, "ativo": True}],
        "total": 1, "page": 1, "page_size": 3, "total_pages": 1,
    }
    mock_vac.return_value = {
        "items": [{"id": 1, "nome": "COVID-19", "alta_complexidade": False, "ativo": True}],
        "total": 1, "page": 1, "page_size": 3, "total_pages": 1,
    }

    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "GESTOR_MUNICIPAL"
    at.session_state["municipio_id"] = "2304400"
    at.session_state["pagina_ativa"] = "municipios"
    at.run()

    assert not at.exception
    assert not [b for b in at.button if b.label == "Editar"]


@patch("municipios_ui.desativar_municipio")
def test_confirmar_desativacao_avisa_o_usuario_no_erro(mock_desativar):
    import municipios_ui

    mock_desativar.side_effect = ApiError("Falha ao desativar.")
    st.session_state.clear()
    st.session_state["municipio_confirmando_id"] = "2304400"

    municipios_ui.confirmar_desativacao("token", "2304400")

    assert st.session_state["municipio_confirmando_id"] == "2304400"


@pytest.mark.parametrize(
    "id_ibge, nome, uf, editando, deve_falhar",
    [
        ("2304400", "Fortaleza", "CE", None, False),
        ("230440", "Fortaleza", "CE", None, True),      # 6 dígitos
        ("23044AA", "Fortaleza", "CE", None, True),     # não numérico
        ("", "Fortaleza", "CE", {"id_ibge": "x"}, False),
        ("2304400", "", "CE", None, True),
        ("2304400", "Fortaleza", "ceara", None, True),
        ("2304400", "Fortaleza", "C1", None, True),
        ("2304400", "Fortaleza", "ce", None, False),    # minúscula é normalizada
    ],
)
def test_validar_formulario_cobre_todas_as_regras(id_ibge, nome, uf, editando, deve_falhar):
    import municipios_ui

    erro = municipios_ui._validar_formulario(id_ibge, nome, uf, editando)
    assert (erro is not None) is deve_falhar


# ============================================================
# REGISTROS
# ============================================================

@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_registros_erro_de_api(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.side_effect = ApiError("Falha ao listar registros.")

    at = _app("registros")
    at.run()

    assert not at.exception
    assert any("Falha ao listar registros." in e.value for e in at.error)


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_registros_renderiza_todos_os_status(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {
        "items": [
            {"id": "1", "data_vacinacao": "2024-01-10", "municipio_vacina_nome": "Fortaleza",
             "vacina_nome": "COVID-19", "status_dado": "VALIDO", "vacina_id": 1},
            {"id": "2", "data_vacinacao": "2024-02-10", "municipio_vacina_nome": None,
             "vacina_nome": None, "status_dado": "DADO_INCONSISTENTE", "vacina_id": 9},
            {"id": "3", "data_vacinacao": None, "municipio_vacina_nome": "Caucaia",
             "vacina_nome": "BCG", "status_dado": "DESLOCAMENTO_INDETERMINADO", "vacina_id": 2},
        ],
        "total": 3, "page": 1, "page_size": 5, "total_pages": 1,
    }

    at = _app("registros")
    at.run()

    assert not at.exception
    texto = " ".join(md.value for md in at.markdown)
    assert "Válido" in texto and "Inconsistente" in texto
    assert "—" in texto, "município ausente deve virar travessão"


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_registros_paginacao_avanca(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {
        "items": [{"id": "1", "data_vacinacao": "2024-01-10",
                   "municipio_vacina_nome": "Fortaleza", "vacina_nome": "COVID-19",
                   "status_dado": "VALIDO", "vacina_id": 1}],
        "total": 20, "page": 1, "page_size": 5, "total_pages": 4,
    }

    at = _app("registros")
    at.run()
    at.button(key="next_reg").click().run()

    assert not at.exception
    assert at.session_state["reg_page"] == 2


@patch("registros_ui.listar_registros")
@patch("registros_ui.listar_vacinas_resumido")
@patch("registros_ui.listar_municipios_resumido")
def test_registros_filtros_vao_para_a_api(mock_mun, mock_vac, mock_reg):
    mock_mun.return_value = _MUNICIPIOS
    mock_vac.return_value = _VACINAS
    mock_reg.return_value = {"items": [], "total": 0, "page": 1, "page_size": 5, "total_pages": 0}

    at = _app("registros", filtro_idade="0-10 anos", filtro_periodo="Período: 2023")
    at.run()

    assert not at.exception
    kwargs = mock_reg.call_args.kwargs
    assert kwargs.get("idade_min") == 0 and kwargs.get("idade_max") == 10
    assert kwargs.get("data_inicio") == "2023-01-01"


def test_registros_sem_token_avisa():
    import registros_ui

    st.session_state.clear()
    registros_ui.render_registros_section()


def test_montar_filtros_sem_periodo_valido():
    from registros_ui import _montar_filtros_query

    params = _montar_filtros_query(
        "Município: todos", "Vacina: todas", "Período: todos", "Faixa etária: todas"
    )
    assert "data_inicio" not in params
