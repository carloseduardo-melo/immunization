"""RF15/RF16 - Alertas de completude de dados.

Lista os meses/municípios que a varredura apontou como fora do padrão esperado e
permite ao administrador tratar cada alerta. A varredura em si roda no backend
(POST /completude/recalcular); esta tela apenas a dispara e mostra o resultado.
"""

import streamlit as st

from api_client import ApiError
from data_cache import alertas_completude, listar_municipios_resumido
from theme import badge_html

# Rótulo exibido e tom do badge de cada status do banco.
STATUS_ROTULOS = {
    "ABERTO": ("Aberto", "danger"),
    "INVESTIGANDO": ("Investigando", "warning"),
    "RESOLVIDO": ("Resolvido", "success"),
    "FALSO_POSITIVO": ("Falso positivo", "neutral"),
}
OPCOES_STATUS = ["Todos"] + [rotulo for rotulo, _ in STATUS_ROTULOS.values()]
_ROTULO_PARA_STATUS = {rotulo: chave for chave, (rotulo, _) in STATUS_ROTULOS.items()}
PAGE_SIZE = 10


def _init_state():
    if "completude_page" not in st.session_state:
        st.session_state["completude_page"] = 1


def _municipios(token):
    try:
        return listar_municipios_resumido(token)
    except ApiError:
        # A tela continua útil sem o seletor de município.
        return []


def _render_filtros(municipios):
    col_status, col_municipio, col_ano = st.columns([1.2, 2, 1])

    with col_status:
        rotulo = st.selectbox("Status", OPCOES_STATUS, key="completude_status")
        status = _ROTULO_PARA_STATUS.get(rotulo)

    with col_municipio:
        opcoes = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
        escolha = st.selectbox("Município", opcoes, key="completude_municipio")
        municipio_id = None
        if escolha != "Todos":
            municipio_id = escolha.split("(")[-1].replace(")", "").strip()

    with col_ano:
        ano = st.number_input(
            "Ano", min_value=0, max_value=2100, value=0, step=1, key="completude_ano"
        )
        ano = int(ano) or None

    return status, municipio_id, ano


def _render_kpis(pagina):
    totais = pagina["totais_por_status"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de alertas", pagina["total"])
    col2.metric("Abertos", totais["ABERTO"])
    col3.metric("Em investigação", totais["INVESTIGANDO"])
    col4.metric("Municípios afetados", pagina["municipios_afetados"])


def _render_linha(alerta):
    colunas = st.columns([1.2, 2.4, 1.4, 1.6, 2.4])
    colunas[0].markdown(f"{alerta['referencia_mes']:02d}/{alerta['referencia_ano']}")
    colunas[1].markdown(alerta.get("municipio_nome") or "—")
    colunas[2].markdown(f"{alerta['total_observado']}")
    rotulo, tom = STATUS_ROTULOS.get(alerta["status"], (alerta["status"], "neutral"))
    colunas[3].markdown(badge_html(rotulo, tom), unsafe_allow_html=True)
    return colunas[4]


def _render_paginacao(pagina):
    total_paginas = max(pagina["total_pages"], 1)
    atual = st.session_state["completude_page"]
    col_info, _, col_anterior, col_proxima = st.columns([6, 3, 0.6, 0.6])
    col_info.caption(f"Página {atual} de {total_paginas} — {pagina['total']} alertas")

    if col_anterior.button("◀", key="completude_anterior", disabled=atual <= 1):
        st.session_state["completude_page"] = atual - 1
        st.rerun()
    if col_proxima.button("▶", key="completude_proxima", disabled=atual >= total_paginas):
        st.session_state["completude_page"] = atual + 1
        st.rerun()


def render_completude_section():
    """RF15/RF16 - Painel de alertas de completude."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar os alertas.")
        return

    _init_state()

    st.markdown(
        '<div class="page-title">⚠️ Alertas de Completude</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="page-subtitle">Meses e municípios com volume de registros fora '
        "da faixa esperada.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        status, municipio_id, ano = _render_filtros(_municipios(token))

    try:
        pagina = alertas_completude(
            token,
            status=status,
            municipio_id=municipio_id,
            ano=ano,
            page=st.session_state["completude_page"],
            page_size=PAGE_SIZE,
        )
    except ApiError as exc:
        st.error(f"Erro ao carregar os alertas de completude: {exc.message}")
        return

    _render_kpis(pagina)

    if not pagina["items"]:
        st.info("Nenhum alerta de completude para os filtros selecionados.")
        return

    st.markdown("<hr>", unsafe_allow_html=True)
    cabecalho = st.columns([1.2, 2.4, 1.4, 1.6, 2.4])
    for coluna, titulo in zip(
        cabecalho, ["Referência", "Município", "Doses", "Status", ""]
    ):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for alerta in pagina["items"]:
        _render_linha(alerta)

    _render_paginacao(pagina)
