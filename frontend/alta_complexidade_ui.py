"""RF18 - Painel de imunobiológicos de alta complexidade.

Uma linha por vacina de alta complexidade, com a taxa de deslocamento e o
município que funciona como centro de referência regional; o expander de cada
linha abre o ranking completo dos municípios de maior aplicação.
"""

import streamlit as st

from api_client import ApiError
from data_cache import alta_complexidade
from theme import badge_html

OPCOES_TOP = [3, 5, 10]


def _formatar_numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _tom_taxa(taxa: float) -> str:
    """Acima de 50% a vacina é majoritariamente aplicada fora do município de
    residência do paciente - o sinal de centro de referência regional."""
    if taxa > 50:
        return "danger"
    if taxa >= 25:
        return "warning"
    return "neutral"


def _render_kpis(itens):
    total_doses = sum(item["total_doses"] for item in itens)
    total_deslocamentos = sum(item["total_deslocamentos"] for item in itens)
    # Ponderada pelo volume: uma vacina com 20 doses não pode pesar o mesmo que
    # uma com 20 mil na taxa geral.
    taxa_geral = (
        round(total_deslocamentos / total_doses * 100, 2) if total_doses else 0.0
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.metric("Vacinas de alta complexidade", len(itens))
    with col2:
        with st.container(border=True):
            st.metric("Doses aplicadas", _formatar_numero(total_doses))
    with col3:
        with st.container(border=True):
            st.metric("Taxa geral de deslocamento", f"{taxa_geral}%")


def _render_ranking(item):
    if not item["municipios"]:
        st.caption("Nenhuma dose registrada para esta vacina no período.")
        return
    for posicao, municipio in enumerate(item["municipios"], start=1):
        linha = st.columns([0.6, 3, 1.6, 1.6])
        linha[0].markdown(f"{posicao}º")
        linha[1].markdown(
            f"{municipio['municipio_nome']} ({municipio['municipio_id']})"
        )
        linha[2].markdown(_formatar_numero(municipio["total_doses"]))
        linha[3].markdown(f"{municipio['percentual']}%")


def _render_vacina(item):
    colunas = st.columns([3, 1.6, 1.6, 2.4])
    colunas[0].markdown(f"**{item['vacina_nome']}**")
    colunas[1].markdown(_formatar_numero(item["total_doses"]))
    colunas[2].markdown(
        badge_html(
            f"{item['taxa_deslocamento']}%", _tom_taxa(item["taxa_deslocamento"])
        ),
        unsafe_allow_html=True,
    )
    colunas[3].markdown(item["centro_referencia_nome"] or "—")

    with st.expander(f"Municípios de aplicação — {item['vacina_nome']}"):
        _render_ranking(item)


def render_alta_complexidade_section():
    """RF18 - Painel de imunobiológicos de alta complexidade."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar este painel.")
        return

    st.markdown(
        '<div class="page-title">🧬 Imunobiológicos de Alta Complexidade</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Taxa de deslocamento de cada vacina e os '
        "municípios que funcionam como centro de referência regional.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        top_municipios = st.selectbox(
            "Municípios por vacina", OPCOES_TOP, key="alta_top_municipios"
        )

    try:
        dados = alta_complexidade(token, top_municipios=int(top_municipios))
    except ApiError as exc:
        st.error(f"Erro ao carregar o painel de alta complexidade: {exc.message}")
        return

    itens = dados["items"]
    if not itens:
        st.info(
            "Nenhuma vacina marcada como alta complexidade. Marque a opção em "
            "Gestão de Municípios & Vacinas."
        )
        return

    _render_kpis(itens)
    st.markdown("<hr>", unsafe_allow_html=True)
    cabecalho = st.columns([3, 1.6, 1.6, 2.4])
    for coluna, titulo in zip(
        cabecalho, ["Vacina", "Doses", "Deslocamento", "Centro de referência"]
    ):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for item in itens:
        _render_vacina(item)
