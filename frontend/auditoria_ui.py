"""RF22 - Consulta do log de auditoria, restrita ao perfil Administrador.

A tela responde a "quem alterou o quê e quando": lista as operações de Update e
Delete gravadas pelo backend (RF21) e, para cada uma, abre a diferença campo a
campo entre o valor antigo e o novo.

O log é somente-leitura em toda a aplicação (RNF09) — por isso esta tela não tem
nenhuma ação de escrita, apenas filtros e paginação.
"""

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from api_client import ApiError
from data_cache import logs_auditoria, usuarios_auditoria
from theme import badge_html

# Rótulo exibido para cada tabela auditada. O valor é o nome real da tabela,
# que é o que o backend espera no filtro.
TABELAS = {
    "Registros de vacinação": "registros_vacinacao",
    "Municípios": "municipios",
    "Vacinas": "vacinas",
}
OPCOES_TABELA = ["Todas"] + list(TABELAS)

ACAO_TONS = {"UPDATE": "warning", "DELETE": "danger"}

PAGE_SIZE = 10

_COLUNAS = [1.6, 1.8, 1.2, 2.4, 2.6]
_CABECALHOS = ["Quando", "Tabela", "Ação", "Registro", "Autor"]


def campos_alterados(valores_antigos, valores_novos) -> list[tuple]:
    """Devolve (campo, antes, depois) apenas dos campos que mudaram.

    É o que torna o log legível: uma edição de município toca um campo entre
    dez, e mostrar o JSON inteiro obrigaria o administrador a caçar a diferença
    no olho. A união das chaves cobre o caso de um dos lados não ter o campo.
    """
    antigos = valores_antigos or {}
    novos = valores_novos or {}
    return [
        (campo, antigos.get(campo), novos.get(campo))
        for campo in sorted(set(antigos) | set(novos))
        if antigos.get(campo) != novos.get(campo)
    ]


def _texto(valor) -> str:
    """Formata um valor do snapshot para leitura na tabela de diferenças.

    `json.dumps` mantém a distinção entre `None`, `false` e a string "false",
    que num log de auditoria não pode se perder.
    """
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False)


def _init_state():
    if "auditoria_page" not in st.session_state:
        st.session_state["auditoria_page"] = 1
    if "auditoria_filtros_anteriores" not in st.session_state:
        # Mesma quádrupla que _render_filtros produz com os valores padrão dos
        # widgets, para o primeiro render não disparar um reset de página.
        st.session_state["auditoria_filtros_anteriores"] = (None, None, None, None)


def _autores(token) -> list[dict]:
    try:
        return usuarios_auditoria(token)
    except ApiError:
        # A tela continua útil sem o seletor de autor.
        return []


def _render_filtros(autores):
    col_usuario, col_tabela, col_de, col_ate = st.columns([2.2, 1.8, 1.2, 1.2])

    with col_usuario:
        emails = [autor["email"] for autor in autores]
        escolha = st.selectbox("Autor", ["Todos"] + emails, key="auditoria_usuario")
        usuario_id = None
        if escolha != "Todos":
            usuario_id = next(a["id"] for a in autores if a["email"] == escolha)

    with col_tabela:
        rotulo = st.selectbox("Tabela", OPCOES_TABELA, key="auditoria_tabela")
        tabela = TABELAS.get(rotulo)

    with col_de:
        data_inicio = st.date_input("De", value=None, key="auditoria_data_inicio")

    with col_ate:
        data_fim = st.date_input("Até", value=None, key="auditoria_data_fim")

    filtros = (
        usuario_id,
        tabela,
        data_inicio.isoformat() if data_inicio else None,
        data_fim.isoformat() if data_fim else None,
    )

    # Trocar qualquer filtro invalida a página atual — senão o administrador
    # pode ficar preso numa página que não existe mais no novo recorte.
    if st.session_state["auditoria_filtros_anteriores"] != filtros:
        st.session_state["auditoria_filtros_anteriores"] = filtros
        st.session_state["auditoria_page"] = 1

    return filtros


def _render_diferenca(log):
    """Valor antigo x valor novo, campo a campo."""
    alteracoes = campos_alterados(log["valores_antigos"], log["valores_novos"])
    if not alteracoes:
        st.caption("Nenhum campo do registro mudou de valor nesta operação.")
        return

    st.dataframe(
        pd.DataFrame(
            [(campo, _texto(antes), _texto(depois)) for campo, antes, depois in alteracoes],
            columns=["Campo", "Antes", "Depois"],
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_linha(log):
    quando = datetime.fromisoformat(log["criado_em"]).strftime("%d/%m/%Y %H:%M")
    colunas = st.columns(_COLUNAS)
    colunas[0].markdown(quando)
    # O rótulo amigável é o que se lê; o nome real da tabela vem junto porque
    # uma investigação de auditoria precisa saber exatamente onde a linha está.
    rotulo = next((r for r, t in TABELAS.items() if t == log["tabela"]), log["tabela"])
    colunas[1].markdown(
        f'{rotulo}<br><span style="font-size:11px;color:#71717a;">{log["tabela"]}</span>',
        unsafe_allow_html=True,
    )
    colunas[2].markdown(
        badge_html(log["acao"], ACAO_TONS.get(log["acao"], "neutral")),
        unsafe_allow_html=True,
    )
    colunas[3].markdown(f'`{log["registro_id"]}`')
    colunas[4].markdown(log["usuario_email"])

    with st.expander("Ver o que mudou"):
        _render_diferenca(log)


def _render_paginacao(pagina):
    total_paginas = max(pagina["total_pages"], 1)
    atual = st.session_state["auditoria_page"]
    col_info, _, col_anterior, col_proxima = st.columns([6, 3, 0.6, 0.6])
    col_info.caption(
        f"Página {atual} de {total_paginas} — {pagina['total']} alteração(ões)"
    )

    if col_anterior.button("◀", key="auditoria_anterior", disabled=atual <= 1):
        st.session_state["auditoria_page"] = atual - 1
        st.rerun()
    if col_proxima.button("▶", key="auditoria_proxima", disabled=atual >= total_paginas):
        st.session_state["auditoria_page"] = atual + 1
        st.rerun()


def render_auditoria_section():
    """RF22 - Painel de consulta do log de auditoria."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para consultar o log de auditoria.")
        return

    st.markdown('<div class="page-title">🔍 Log de Auditoria</div>', unsafe_allow_html=True)

    # O backend já recusa perfis não-ADMIN (403). A checagem aqui evita a
    # chamada inútil e explica o motivo em vez de exibir um erro de API.
    if st.session_state.get("role") != "ADMIN":
        st.error("A consulta ao log de auditoria é restrita ao perfil Administrador.")
        return

    _init_state()

    st.markdown(
        '<div class="page-subtitle">Toda alteração e exclusão de dado de negócio, '
        "com o valor anterior e o valor resultante.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        usuario_id, tabela, data_inicio, data_fim = _render_filtros(_autores(token))

    try:
        pagina = logs_auditoria(
            token,
            usuario_id=usuario_id,
            tabela=tabela,
            data_inicio=data_inicio,
            data_fim=data_fim,
            page=st.session_state["auditoria_page"],
            page_size=PAGE_SIZE,
        )
    except ApiError as exc:
        st.error(f"Erro ao carregar o log de auditoria: {exc.message}")
        return

    if not pagina["items"]:
        st.info("Nenhuma alteração registrada para os filtros selecionados.")
        return

    st.markdown("<hr>", unsafe_allow_html=True)
    cabecalho = st.columns(_COLUNAS)
    for coluna, titulo in zip(cabecalho, _CABECALHOS):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for log in pagina["items"]:
        _render_linha(log)

    _render_paginacao(pagina)
