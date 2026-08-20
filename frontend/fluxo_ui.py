"""RF13 (Painel de fluxo intermunicipal) e RF14 (Ranking de municípios-polo
e de evasão).

Nota de desempenho — o motivo do desenho desta tela:

Os dados reais têm pacientes residentes em 27 UFs vacinados no Ceará, o que dá
~3.100 municípios de origem e ~2.800 de destino. Um mapa de calor cruzando
todos eles seria uma matriz de ~8,8 milhões de células — ilegível para o
usuário e, renderizada como HTML, ~1,3 GB enviados ao navegador (o que estourava
o limite de mensagem do Streamlit). Apenas 0,4% dessas células têm algum fluxo.

Por isso o mapa de calor cobre somente os N maiores fluxos (o recorte que de
fato informa a decisão de gestão), e o detalhamento completo é paginado. A
seleção do "top N" e a paginação acontecem no banco, via SQL — o navegador
recebe apenas a página exibida.
"""

import pandas as pd
import streamlit as st

from api_client import ApiError
from data_cache import fluxo_intermunicipal, listar_municipios_resumido, listar_vacinas_resumido, ranking_fluxo
from theme import COLORS, badge_html

# Teto de segurança do mapa de calor. Com o "top N" máximo (25) a matriz tem no
# máximo 25x25; esta constante é uma rede de proteção para que nenhuma mudança
# futura volte a gerar uma matriz capaz de estourar o limite de mensagem.
MAX_CELULAS_HEATMAP = 2_500
NIVEIS_INTENSIDADE = 10

OPCOES_TOP_N = [10, 15, 20, 25]
OPCOES_PAGE_SIZE = [10, 25, 50, 100]


def _formatar_numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _css_escala_calor() -> str:
    """Gera uma vez as classes de intensidade do mapa de calor.

    Antes cada célula carregava seu próprio `style=` inline (~156 bytes). Com
    classes, a escala é declarada uma única vez e cada célula passa a custar
    ~25 bytes, mantendo exatamente o mesmo resultado visual.
    """
    r1, g1, b1 = _hex_to_rgb(COLORS["primary"])
    regras = [
        ".hm{border-collapse:separate;border-spacing:3px;}",
        f".hm th{{padding:6px 10px;font-size:12px;color:{COLORS['muted']};white-space:nowrap;font-weight:600;}}",
        ".hm th.o{text-align:left;}",
        f".hm td{{padding:6px 10px;text-align:right;font-size:13px;border-radius:4px;white-space:nowrap;color:{COLORS['ink']};}}",
        f".hm td.o{{text-align:left;font-weight:600;color:{COLORS['text']};background:transparent;}}",
    ]
    for nivel in range(NIVEIS_INTENSIDADE):
        fracao = nivel / (NIVEIS_INTENSIDADE - 1)
        r = round(255 + (r1 - 255) * fracao)
        g = round(255 + (g1 - 255) * fracao)
        b = round(255 + (b1 - 255) * fracao)
        cor_texto = "#ffffff" if fracao > 0.55 else COLORS["ink"]
        regras.append(f".hm td.h{nivel}{{background-color:rgb({r},{g},{b});color:{cor_texto};}}")
    return "<style>" + "".join(regras) + "</style>"


def _nivel_intensidade(valor: float, maximo: float) -> int:
    if maximo <= 0:
        return 0
    return min(int(valor / maximo * (NIVEIS_INTENSIDADE - 1) + 0.5), NIVEIS_INTENSIDADE - 1)


def _renderizar_mapa_calor(df_pivot: pd.DataFrame):
    if df_pivot.empty:
        st.info("Não há fluxo suficiente para montar o mapa de calor.")
        return

    if df_pivot.size > MAX_CELULAS_HEATMAP:  # rede de proteção, não deve ocorrer
        st.warning("Recorte muito amplo para o mapa de calor. Reduza o Top N ou aplique filtros.")
        return

    maximo = float(df_pivot.to_numpy().max())

    cabecalho = "".join(f"<th>{destino}</th>" for destino in df_pivot.columns)
    linhas = [f"<tr><th class=o>Origem \\ Destino</th>{cabecalho}</tr>"]
    for origem, linha in df_pivot.iterrows():
        celulas = "".join(
            f"<td class=h{_nivel_intensidade(valor, maximo)}>{_formatar_numero(valor)}</td>"
            for valor in linha
        )
        linhas.append(f"<tr><td class=o>{origem}</td>{celulas}</tr>")

    st.markdown(
        _css_escala_calor()
        + f"<div style='overflow-x:auto;'><table class=hm>{''.join(linhas)}</table></div>",
        unsafe_allow_html=True,
    )


def _init_state():
    defaults = {"fluxo_page": 1, "fluxo_top_n": 15, "fluxo_page_size": 25}
    for chave, valor in defaults.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


def _opcoes_apoio(token: str):
    """Listas de apoio dos seletores, servidas pelo cache (ver data_cache)."""
    try:
        municipios = listar_municipios_resumido(token)
    except ApiError:
        municipios = []
    try:
        vacinas = listar_vacinas_resumido(token)
    except ApiError:
        vacinas = []
    return municipios, vacinas


def _filtro_vacina(vacinas, key_prefix: str):
    opcoes = ["Todas"] + [f"{nome} (ID: {vid})" for vid, nome in vacinas]
    escolha = st.selectbox("Imunobiológico", opcoes, key=f"{key_prefix}_vacina")
    if escolha == "Todas":
        return None
    return int(escolha.split("ID: ")[-1].replace(")", "").strip())


def _filtro_periodo(key_prefix: str):
    col1, col2 = st.columns(2)
    data_inicio = col1.date_input("De", value=None, key=f"{key_prefix}_data_inicio")
    data_fim = col2.date_input("Até", value=None, key=f"{key_prefix}_data_fim")
    return (
        data_inicio.isoformat() if data_inicio else None,
        data_fim.isoformat() if data_fim else None,
    )


def render_fluxo_intermunicipal_section():
    """RF13 - Mapa de calor dos maiores fluxos + tabela paginada origem x destino."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar o fluxo intermunicipal.")
        return

    _init_state()
    municipios, vacinas = _opcoes_apoio(token)

    st.markdown('<div class="page-title">🔀 Fluxo Intermunicipal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">'
        "Mobilidade vacinal entre o município de residência (origem) e o município "
        "de aplicação (destino) das doses.</div>",
        unsafe_allow_html=True,
    )

    # --- FILTROS (aplicados no banco, antes de qualquer agregação) ---
    with st.container(border=True):
        col1, col2, col3 = st.columns([1.4, 2, 1.4])
        with col1:
            vacina_id = _filtro_vacina(vacinas, "fluxo")
        with col2:
            data_inicio, data_fim = _filtro_periodo("fluxo")
        with col3:
            opcoes_mun = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
            escolha_mun = st.selectbox("Município (origem ou destino)", opcoes_mun, key="fluxo_municipio")
            municipio_id = None
            if escolha_mun != "Todos":
                municipio_id = escolha_mun.split("(")[-1].replace(")", "").strip()

    filtros = dict(
        vacina_id=vacina_id, data_inicio=data_inicio, data_fim=data_fim, municipio_id=municipio_id
    )

    top_n = st.session_state["fluxo_top_n"]

    with st.spinner("Calculando fluxo intermunicipal..."):
        try:
            # Página 1 ordenada por volume = os N maiores fluxos do recorte.
            topo = fluxo_intermunicipal(token, page=1, page_size=top_n, **filtros)
        except ApiError as exc:
            st.error(f"Erro ao carregar o fluxo intermunicipal: {exc.message}")
            return

    total_pares = topo.get("total", 0)
    if not topo.get("items"):
        st.info("Não há deslocamentos registrados para os filtros selecionados.")
        return

    # --- MAPA DE CALOR (somente os N maiores fluxos) ---
    cab_esq, cab_dir = st.columns([3, 1])
    with cab_esq:
        st.markdown('<div class="card-title">Mapa de calor: origem x destino</div>', unsafe_allow_html=True)
    with cab_dir:
        novo_top = st.selectbox(
            "Top N fluxos", OPCOES_TOP_N, index=OPCOES_TOP_N.index(top_n), key="fluxo_sel_top_n"
        )
        if novo_top != top_n:
            st.session_state["fluxo_top_n"] = novo_top
            st.rerun()

    st.caption(
        f"Exibindo os {len(topo['items'])} maiores fluxos de um total de "
        f"{_formatar_numero(total_pares)} pares origem/destino "
        f"({_formatar_numero(topo.get('total_doses', 0))} doses no recorte)."
    )

    df_topo = pd.DataFrame(topo["items"])
    df_pivot = df_topo.pivot_table(
        index="municipio_origem_nome",
        columns="municipio_destino_nome",
        values="total_doses",
        aggfunc="sum",
        fill_value=0,
    )
    _renderizar_mapa_calor(df_pivot)

    # --- TABELA PAGINADA (detalhamento) ---
    st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
    tab_esq, tab_dir = st.columns([3, 1])
    with tab_esq:
        st.markdown('<div class="card-title">Detalhamento por par de municípios</div>', unsafe_allow_html=True)
    with tab_dir:
        page_size = st.selectbox(
            "Registros por página",
            OPCOES_PAGE_SIZE,
            index=OPCOES_PAGE_SIZE.index(st.session_state["fluxo_page_size"]),
            key="fluxo_sel_page_size",
        )
        if page_size != st.session_state["fluxo_page_size"]:
            st.session_state["fluxo_page_size"] = page_size
            st.session_state["fluxo_page"] = 1
            st.rerun()

    page = st.session_state["fluxo_page"]
    try:
        pagina = fluxo_intermunicipal(token, page=page, page_size=page_size, **filtros)
    except ApiError as exc:
        st.error(f"Erro ao carregar o detalhamento: {exc.message}")
        return

    df_tabela = pd.DataFrame(pagina["items"]).rename(
        columns={
            "municipio_origem_nome": "Origem (residência)",
            "municipio_destino_nome": "Destino (aplicação)",
            "total_doses": "Doses",
        }
    )[["Origem (residência)", "Destino (aplicação)", "Doses"]]
    st.dataframe(df_tabela, use_container_width=True, hide_index=True)

    total_pages = max(pagina.get("total_pages", 1), 1)
    c_info, _, c_prev, c_next = st.columns([6, 3, 0.6, 0.6])
    c_info.caption(
        f"Página {pagina.get('page', 1)} de {total_pages} — "
        f"{_formatar_numero(total_pares)} pares no total"
    )
    if c_prev.button("\\<", disabled=page <= 1, key="fluxo_prev", use_container_width=True):
        st.session_state["fluxo_page"] = page - 1
        st.rerun()
    if c_next.button("\\>", disabled=page >= total_pages, key="fluxo_next", use_container_width=True):
        st.session_state["fluxo_page"] = page + 1
        st.rerun()


def _tabela_ranking(itens: list) -> str:
    linhas = []
    for item in itens:
        saldo = item["saldo_liquido"]
        tom = "success" if saldo > 0 else ("warning" if saldo < 0 else "neutral")
        rotulo = _formatar_numero(saldo) if saldo <= 0 else f"+{_formatar_numero(saldo)}"
        linhas.append(
            "<tr>"
            f"<td style='padding:8px 4px;font-size:13px;color:{COLORS['text']};'>{item['municipio_nome']}</td>"
            f"<td style='padding:8px 4px;font-size:13px;text-align:right;color:{COLORS['muted']};'>{_formatar_numero(item['total_recebido'])}</td>"
            f"<td style='padding:8px 4px;font-size:13px;text-align:right;color:{COLORS['muted']};'>{_formatar_numero(item['total_perdido'])}</td>"
            f"<td style='padding:8px 4px;text-align:right;'>{badge_html(rotulo, tom)}</td>"
            "</tr>"
        )
    cabecalho = (
        "<tr>"
        f"<th style='padding:4px;text-align:left;font-size:11px;color:{COLORS['muted']};text-transform:uppercase;'>Município</th>"
        f"<th style='padding:4px;text-align:right;font-size:11px;color:{COLORS['muted']};text-transform:uppercase;'>Recebido</th>"
        f"<th style='padding:4px;text-align:right;font-size:11px;color:{COLORS['muted']};text-transform:uppercase;'>Perdido</th>"
        f"<th style='padding:4px;text-align:right;font-size:11px;color:{COLORS['muted']};text-transform:uppercase;'>Saldo</th>"
        "</tr>"
    )
    return f"<table style='width:100%;border-collapse:collapse;'>{cabecalho}{''.join(linhas)}</table>"


def render_fluxo_ranking_section():
    """RF14 - Ranking de municípios-polo (saldo positivo) e de evasão (saldo negativo)."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar o ranking de municípios.")
        return

    _, vacinas = _opcoes_apoio(token)

    st.markdown(
        '<div class="page-subtitle" style="margin-top:0;">'
        "Comparativo entre municípios que mais recebem pacientes de fora (polo) e os "
        "que mais perdem pacientes para outros municípios (evasão), pelo saldo líquido "
        "(doses recebidas - doses perdidas).</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            vacina_id = _filtro_vacina(vacinas, "ranking")
        with col2:
            data_inicio, data_fim = _filtro_periodo("ranking")
        with col3:
            limit = st.number_input("Top N", min_value=1, max_value=50, value=10, key="ranking_limit")

    with st.spinner("Calculando ranking..."):
        try:
            dados = ranking_fluxo(
                token,
                vacina_id=vacina_id,
                data_inicio=data_inicio,
                data_fim=data_fim,
                limit=int(limit),
            )
        except ApiError as exc:
            st.error(f"Erro ao carregar o ranking de municípios: {exc.message}")
            return

    top_polo = dados.get("top_polo", [])
    top_evasao = dados.get("top_evasao", [])

    if not top_polo and not top_evasao:
        st.info("Não há deslocamentos registrados para os filtros selecionados.")
        return

    col_polo, col_evasao = st.columns(2)
    with col_polo:
        with st.container(border=True):
            st.markdown('<div class="card-title">🏆 Municípios-polo (maior saldo)</div>', unsafe_allow_html=True)
            if top_polo:
                st.markdown(_tabela_ranking(top_polo), unsafe_allow_html=True)
            else:
                st.caption("Sem dados.")
    with col_evasao:
        with st.container(border=True):
            st.markdown('<div class="card-title">⚠️ Municípios de evasão (menor saldo)</div>', unsafe_allow_html=True)
            if top_evasao:
                st.markdown(_tabela_ranking(top_evasao), unsafe_allow_html=True)
            else:
                st.caption("Sem dados.")
