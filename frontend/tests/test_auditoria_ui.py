"""RF22 - tela de consulta do log de auditoria (restrita ao Administrador)."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import auditoria_ui
from api_client import ApiError

_USUARIOS = [
    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "email": "admin@saude.gov.br"},
    {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "email": "gestor@saude.gov.br"},
]


def _pagina_logs(items=None):
    if items is None:
        items = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "tabela": "municipios",
                "registro_id": "2304400",
                "acao": "UPDATE",
                "usuario_id": _USUARIOS[0]["id"],
                "usuario_email": "admin@saude.gov.br",
                "valores_antigos": {"nome": "Fortaleza", "uf": "CE", "polo": False},
                "valores_novos": {"nome": "Fortaleza Norte", "uf": "CE", "polo": True},
                "criado_em": "2026-08-20T10:30:00",
            }
        ]
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": 10,
        "total_pages": 1 if items else 0,
    }


def _abrir(role="ADMIN", municipio_id=None):
    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = role
    at.session_state["municipio_id"] = municipio_id
    at.session_state["pagina_ativa"] = "auditoria"
    return at


# ==========================================
# Diferença legível entre valor antigo e novo
# ==========================================


def test_campos_alterados_ignora_o_que_nao_mudou():
    alterados = auditoria_ui.campos_alterados(
        {"nome": "Fortaleza", "uf": "CE", "polo": False},
        {"nome": "Fortaleza Norte", "uf": "CE", "polo": True},
    )

    assert alterados == [("nome", "Fortaleza", "Fortaleza Norte"), ("polo", False, True)]


def test_campos_alterados_cobre_chave_que_so_existe_de_um_lado():
    alterados = auditoria_ui.campos_alterados({"a": 1}, {"a": 1, "b": 2})

    assert alterados == [("b", None, 2)]


def test_campos_alterados_com_dicionarios_vazios():
    assert auditoria_ui.campos_alterados(None, None) == []


# ==========================================
# Listagem
# ==========================================


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_tela_lista_as_alteracoes(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    assert mock_logs.called
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Log de Auditoria" in textos
    assert "municipios" in textos
    assert "2304400" in textos
    assert "admin@saude.gov.br" in textos
    assert "20/08/2026" in textos


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_tela_mostra_apenas_os_campos_alterados(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    linhas = [tuple(linha) for linha in at.dataframe[0].value.itertuples(index=False)]
    assert linhas == [("nome", "Fortaleza", "Fortaleza Norte"), ("polo", "false", "true")]


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_exclusao_logica_aparece_como_ativo_de_true_para_false(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs(
        [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "tabela": "vacinas",
                "registro_id": "7",
                "acao": "DELETE",
                "usuario_id": _USUARIOS[0]["id"],
                "usuario_email": "admin@saude.gov.br",
                "valores_antigos": {"id": 7, "nome": "BCG", "ativo": True},
                "valores_novos": {"id": 7, "nome": "BCG", "ativo": False},
                "criado_em": "2026-08-21T08:00:00",
            }
        ]
    )
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    linhas = [tuple(linha) for linha in at.dataframe[0].value.itertuples(index=False)]
    assert linhas == [("ativo", "true", "false")]


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_alteracao_sem_diferenca_avisa_em_vez_de_tabela_vazia(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs(
        [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "tabela": "municipios",
                "registro_id": "2304400",
                "acao": "UPDATE",
                "usuario_id": _USUARIOS[0]["id"],
                "usuario_email": "admin@saude.gov.br",
                "valores_antigos": {"nome": "Fortaleza"},
                "valores_novos": {"nome": "Fortaleza"},
                "criado_em": "2026-08-22T08:00:00",
            }
        ]
    )
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    assert not at.dataframe
    assert any("Nenhum campo" in (c.value or "") for c in at.caption)


# ==========================================
# Filtros
# ==========================================


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_filtro_de_usuario_e_repassado_a_api(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()
    at.selectbox(key="auditoria_usuario").select("gestor@saude.gov.br").run()

    assert not at.exception
    assert mock_logs.call_args.kwargs["usuario_id"] == _USUARIOS[1]["id"]


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_filtro_de_tabela_e_repassado_a_api(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()
    at.selectbox(key="auditoria_tabela").select("Vacinas").run()

    assert not at.exception
    assert mock_logs.call_args.kwargs["tabela"] == "vacinas"


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_filtro_de_periodo_e_repassado_a_api(mock_logs, mock_usuarios):
    from datetime import date

    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()
    at.date_input(key="auditoria_data_inicio").set_value(date(2026, 8, 1)).run()
    at.date_input(key="auditoria_data_fim").set_value(date(2026, 8, 31)).run()

    assert not at.exception
    assert mock_logs.call_args.kwargs["data_inicio"] == "2026-08-01"
    assert mock_logs.call_args.kwargs["data_fim"] == "2026-08-31"


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_sem_filtros_a_api_recebe_none(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    kwargs = mock_logs.call_args.kwargs
    assert kwargs["usuario_id"] is None
    assert kwargs["tabela"] is None
    assert kwargs["data_inicio"] is None
    assert kwargs["data_fim"] is None


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_trocar_filtro_reseta_a_pagina_para_1(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()
    at.session_state["auditoria_page"] = 3

    at.selectbox(key="auditoria_tabela").select("Vacinas").run()

    assert not at.exception
    assert mock_logs.call_args.kwargs["page"] == 1


# ==========================================
# Paginação, estados vazios e erros
# ==========================================


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_paginacao_avanca_e_volta(mock_logs, mock_usuarios):
    # Duas instâncias de AppTest (uma por sentido), pelo mesmo motivo descrito
    # em test_completude_ui.py: o CookieController interfere no registro do
    # clique na segunda chamada de .run() sobre a mesma instância.
    pagina = _pagina_logs()
    pagina["total"] = 25
    pagina["total_pages"] = 3
    mock_logs.return_value = pagina
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()
    at.button(key="auditoria_proxima").click().run()
    assert mock_logs.call_args.kwargs["page"] == 2

    at2 = _abrir()
    at2.session_state["auditoria_page"] = 2
    at2.run()
    at2.button(key="auditoria_anterior").click().run()
    assert mock_logs.call_args.kwargs["page"] == 1


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_lista_vazia_mostra_aviso(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs([])
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Nenhuma alteração" in (i.value or "") for i in at.info)


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_erro_da_api_exibe_mensagem(mock_logs, mock_usuarios):
    mock_logs.side_effect = ApiError("Servidor indisponível.")
    mock_usuarios.return_value = _USUARIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("auditoria_ui.usuarios_auditoria")
@patch("auditoria_ui.logs_auditoria")
def test_erro_ao_carregar_usuarios_nao_quebra_a_tela(mock_logs, mock_usuarios):
    mock_logs.return_value = _pagina_logs()
    mock_usuarios.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert mock_logs.called


@patch("auditoria_ui.logs_auditoria")
@patch("auditoria_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_logs):
    import streamlit as st

    st.session_state.clear()
    auditoria_ui.render_auditoria_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para consultar o log de auditoria."
    )
    mock_logs.assert_not_called()


# ==========================================
# RF22 - acesso restrito ao perfil Administrador
# ==========================================


@patch("auditoria_ui.logs_auditoria")
def test_perfil_nao_admin_nao_consulta_o_log(mock_logs):
    at = _abrir(role="GESTOR_ESTADUAL").run()

    assert not at.exception
    assert not mock_logs.called
    assert any("Administrador" in (e.value or "") for e in at.error)


def test_menu_mostra_a_auditoria_apenas_para_admin():
    with patch("auditoria_ui.usuarios_auditoria") as mock_usuarios, patch(
        "auditoria_ui.logs_auditoria"
    ) as mock_logs:
        mock_logs.return_value = _pagina_logs()
        mock_usuarios.return_value = _USUARIOS

        admin = _abrir().run()
        assert "nav_auditoria" in [b.key for b in admin.button]

    gestor = AppTest.from_file("app.py")
    gestor.session_state["token"] = "faketoken"
    gestor.session_state["role"] = "GESTOR_ESTADUAL"
    gestor.session_state["municipio_id"] = None
    gestor.session_state["pagina_ativa"] = "dashboard"
    with patch("ui_dashboard.render_dashboard_section"):
        gestor.run()

    assert "nav_auditoria" not in [b.key for b in gestor.button]
