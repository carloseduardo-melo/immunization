import pandas as pd
import streamlit as st

from api_client import ApiError
from data_cache import listar_municipios_resumido, listar_vacinas_resumido, resumo_dashboard
from fluxo_ui import render_fluxo_ranking_section


def _inject_styles():
    st.markdown(
        """
        <style>
        .page-title {
            font-size: 24px;
            font-weight: 600;
            color: #18181b;
            margin-bottom: 4px;
        }
        .page-subtitle {
            font-size: 14px;
            color: #71717a;
            margin-top: 0px;
            margin-bottom: 24px;
        }
        .metric-card {
            background-color: #ffffff;
            border: 1px solid #e4e4e7;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .metric-title {
            font-size: 14px;
            color: #52525b;
            font-weight: 500;
            margin-bottom: 8px;
        }
        .metric-value {
            font-size: 28px;
            font-weight: 700;
            color: #18181b;
        }
        .metric-value.highlight {
            color: #5b5bf6;
        }
        .metric-value.warning {
            color: #b45309;
        }
        /* Ajuste nativo das métricas do Streamlit */
        [data-testid="stMetricValue"] {
            font-size: 26px !important;
            font-weight: 700 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _carregar_dados_apoio(token: str):
    """Listas de municípios e vacinas para os filtros, servidas pelo cache.

    Antes ficavam em `st.session_state`, o que mantinha os objetos completos da
    API presos em memória por toda a sessão de cada usuário. O cache do
    Streamlit é compartilhado entre sessões e expira sozinho (ver data_cache).
    """
    try:
        municipios = listar_municipios_resumido(token)
    except ApiError:
        municipios = []
    try:
        vacinas = listar_vacinas_resumido(token)
    except ApiError:
        vacinas = []
    return municipios, vacinas


def _render_visao_geral(token: str, municipios, vacinas):
    """RF23 - KPIs e série temporal mensal (residentes vs. deslocados)."""
    # --- FILTROS GLOBAIS ---
    opcoes_mun = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
    opcoes_vac = ["Todas"] + [f"{nome} (ID: {vid})" for vid, nome in vacinas]
    opcoes_ano = ["Todos", "2026", "2025", "2024", "2023"]

    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        filtro_mun_raw = col1.selectbox("Município de Aplicação", opcoes_mun)
        filtro_vac_raw = col2.selectbox("Imunobiológico", opcoes_vac)
        filtro_ano_raw = col3.selectbox("Ano de Referência", opcoes_ano)

    # Limpeza dos filtros para enviar à API
    mun_id = None
    if filtro_mun_raw != "Todos":
        mun_id = filtro_mun_raw.split("(")[-1].replace(")", "").strip()

    vac_id = None
    if filtro_vac_raw != "Todas":
        vac_id = int(filtro_vac_raw.split("ID: ")[-1].replace(")", "").strip())

    ano_val = None
    if filtro_ano_raw != "Todos":
        ano_val = int(filtro_ano_raw)

    # --- BUSCA DE DADOS ---
    with st.spinner("Analisando métricas..."):
        try:
            dados = resumo_dashboard(token, municipio_id=mun_id, vacina_id=vac_id, ano=ano_val)
            kpis = dados.get("kpis", {})
            grafico_raw = dados.get("grafico", [])
        except ApiError as exc:
            st.error(f"Erro ao carregar o dashboard: {exc.message}")
            return

    # --- CARDS DE INDICADORES (RF23) ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        with st.container(border=True):
            st.metric("💉 Total de Doses", f"{kpis.get('total_doses', 0):,}".replace(",", "."))
    with c2:
        with st.container(border=True):
            st.metric("🚗 Total de Deslocamentos", f"{kpis.get('total_deslocamentos', 0):,}".replace(",", "."))
    with c3:
        with st.container(border=True):
            st.metric("📈 Taxa de Mobilidade", f"{kpis.get('taxa_mobilidade', 0)}%")
    with c4:
        with st.container(border=True):
            st.metric("⚠️ Dados Inconsistentes", f"{kpis.get('total_inconsistentes', 0):,}".replace(",", "."))

    st.markdown("---")

    # --- GRÁFICO DE LINHAS (RF23) ---
    st.markdown('<div style="font-weight: 600; color: #3f3f46; margin-bottom: 16px;">Evolução: Residentes vs. Pacientes Deslocados</div>', unsafe_allow_html=True)

    if not grafico_raw:
        st.info("Não há dados suficientes para gerar o gráfico no período e filtros selecionados.")
    else:
        df_chart = pd.DataFrame(grafico_raw)

        # Mapeando os valores booleanos para labels legíveis
        mapa_deslocamento = {
            True: 'Deslocados (Origem Externa)',
            False: 'Residentes (Demanda Interna)',
            None: 'Deslocamento Indeterminado'
        }
        df_chart['Tipo'] = df_chart['deslocou'].map(mapa_deslocamento)

        # Formatando para pivot table (Mês no eixo X, Tipos nas colunas, Total nos valores)
        df_pivot = df_chart.pivot_table(index='mes', columns='Tipo', values='total', fill_value=0)

        # Renderiza o gráfico nativo do Streamlit
        st.line_chart(df_pivot, height=350, use_container_width=True)


def render_dashboard_section():
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar o dashboard.")
        return

    _inject_styles()
    municipios, vacinas = _carregar_dados_apoio(token)

    st.markdown('<div class="page-title">📊 Visão Geral do Ceará</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Indicadores agregados de imunização e mobilidade vacinal.</div>', unsafe_allow_html=True)

    _render_visao_geral(token, municipios, vacinas)

    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="card-title">🏆 Ranking de municípios-polo e de evasão</div>', unsafe_allow_html=True)
    render_fluxo_ranking_section()


if __name__ == "__main__":
    render_dashboard_section()
