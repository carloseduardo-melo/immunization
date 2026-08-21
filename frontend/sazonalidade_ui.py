"""RF17 - Painel de sazonalidade.

Mostra o volume de doses por mês do ano (Jan..Dez), consolidando todos os anos
do recorte. A série cronológica ano-a-mês já está no Dashboard Geral; aqui a
pergunta é "em qual mês do ano concentrar a campanha".

O eixo do gráfico usa rótulos "01 Jan", "02 Fev"...: o eixo nominal do Streamlit
ordena alfabeticamente, e o prefixo numérico é o que garante a ordem
cronológica sem depender do comportamento padrão do componente.
"""

import pandas as pd
import streamlit as st

from api_client import ApiError
from data_cache import listar_municipios_resumido, listar_vacinas_resumido, sazonalidade

OPCOES_ANO = ["Todos", "2026", "2025", "2024", "2023", "2022", "2021", "2020"]


def _formatar_numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _dados_apoio(token):
    """Listas dos seletores. A tela continua útil se alguma delas falhar."""
    try:
        municipios = listar_municipios_resumido(token)
    except ApiError:
        municipios = []
    try:
        vacinas = listar_vacinas_resumido(token)
    except ApiError:
        vacinas = []
    return municipios, vacinas


def _render_filtros(municipios, vacinas):
    opcoes_mun = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
    opcoes_vac = ["Todas"] + [f"{nome} (ID: {vid})" for vid, nome in vacinas]

    with st.container(border=True):
        col_vac, col_mun, col_de, col_ate = st.columns([2, 2, 1, 1])
        vac_raw = col_vac.selectbox("Imunobiológico", opcoes_vac, key="saz_vacina")
        mun_raw = col_mun.selectbox(
            "Município de Aplicação", opcoes_mun, key="saz_municipio"
        )
        ano_inicio_raw = col_de.selectbox("De (ano)", OPCOES_ANO, key="saz_ano_inicio")
        ano_fim_raw = col_ate.selectbox("Até (ano)", OPCOES_ANO, key="saz_ano_fim")

    vacina_id = None
    if vac_raw != "Todas":
        vacina_id = int(vac_raw.split("ID: ")[-1].replace(")", "").strip())

    municipio_id = None
    if mun_raw != "Todos":
        municipio_id = mun_raw.split("(")[-1].replace(")", "").strip()

    ano_inicio = None if ano_inicio_raw == "Todos" else int(ano_inicio_raw)
    ano_fim = None if ano_fim_raw == "Todos" else int(ano_fim_raw)

    return vacina_id, municipio_id, ano_inicio, ano_fim


def _render_kpis(kpis):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.metric("Mês de pico", kpis["mes_pico_nome"])
    with col2:
        with st.container(border=True):
            st.metric("Mês de vale", kpis["mes_vale_nome"])
    with col3:
        with st.container(border=True):
            amplitude_texto = (
                "—" if kpis["amplitude"] == 0 else f"{kpis['amplitude']:.1f}x"
            )
            st.metric(
                "Amplitude",
                amplitude_texto,
                help="Pico dividido pelo vale. Travessão quando o mês de vale "
                "não teve nenhuma dose - a amplitude não é definida.",
            )
    with col4:
        with st.container(border=True):
            st.metric("Total do período", _formatar_numero(kpis["total_periodo"]))


def _render_grafico(meses):
    dados = pd.DataFrame(
        {
            "Mês": [f"{mes['mes']:02d} {mes['nome_mes']}" for mes in meses],
            "Doses": [mes["total_doses"] for mes in meses],
        }
    ).set_index("Mês")
    st.bar_chart(dados, height=340, use_container_width=True)


def _marca(mes, kpis) -> str:
    if mes["mes"] == kpis["mes_pico"]:
        return "▲ pico"
    if mes["mes"] == kpis["mes_vale"]:
        return "▼ vale"
    return ""


def _render_tabela(meses, kpis):
    cabecalho = st.columns([1.5, 2, 2, 1.5])
    for coluna, titulo in zip(cabecalho, ["Mês", "Doses", "Índice", ""]):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for mes in meses:
        colunas = st.columns([1.5, 2, 2, 1.5])
        colunas[0].markdown(mes["nome_mes"])
        colunas[1].markdown(_formatar_numero(mes["total_doses"]))
        colunas[2].markdown(f"{mes['indice_sazonalidade']:.2f}")
        colunas[3].markdown(_marca(mes, kpis))


def render_sazonalidade_section():
    """RF17 - Painel de sazonalidade."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar a sazonalidade.")
        return

    st.markdown(
        '<div class="page-title">📅 Sazonalidade da Vacinação</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Volume de doses por mês do ano, consolidando '
        "todo o período filtrado. O índice compara cada mês com a média mensal "
        "(1,00 = mês médio).</div>",
        unsafe_allow_html=True,
    )

    municipios, vacinas = _dados_apoio(token)
    vacina_id, municipio_id, ano_inicio, ano_fim = _render_filtros(municipios, vacinas)

    try:
        dados = sazonalidade(
            token,
            vacina_id=vacina_id,
            municipio_id=municipio_id,
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
        )
    except ApiError as exc:
        st.error(f"Erro ao carregar o painel de sazonalidade: {exc.message}")
        return

    kpis = dados["kpis"]
    if kpis["total_periodo"] == 0:
        st.info("Não há registros de vacinação para os filtros selecionados.")
        return

    _render_kpis(kpis)
    st.markdown("<hr>", unsafe_allow_html=True)
    _render_grafico(dados["meses"])
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    _render_tabela(dados["meses"], kpis)
