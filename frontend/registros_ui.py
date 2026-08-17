from datetime import date
from typing import Any

import streamlit as st

from api_client import (
    ApiError,
    criar_registro,
    listar_municipios,
    listar_registros,
    listar_vacinas,
)

_BADGE_TONES = {
    "success": ("#dcfce7", "#15803d"), # Válido
    "warning": ("#fef3c7", "#b45309"), # Inconsistente
    "neutral": ("#f4f4f5", "#52525b"), # Indeterminado / Inativo
}


def _badge_html(label: str, tone: str) -> str:
    bg, color = _BADGE_TONES.get(tone, _BADGE_TONES["neutral"])
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'font-size:12px;font-weight:500;background:{bg};color:{color};">{label}</span>'
    )


def _inject_styles():
    st.markdown(
        """
        <style>
        /* --- TIPOGRAFIA E CABEÇALHOS --- */
        .registros-card-title {
            font-size: 15px;
            font-weight: 600;
            color: #3f3f46;
            margin-bottom: 16px;
        }
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
        
        /* --- CORES E BOTÕES --- */
        button[kind="primary"] {
            background-color: #5b5bf6 !important;
            border-color: #5b5bf6 !important;
            color: #ffffff !important;
            border-radius: 6px !important;
            font-weight: 500 !important;
        }
        button[kind="primary"]:hover {
            background-color: #4f46e5 !important;
        }
        
        button[kind="secondary"] {
            background-color: #ffffff !important;
            border: 1px solid #e4e4e7 !important;
            color: #3f3f46 !important;
            border-radius: 6px !important;
            font-size: 13px !important;
            min-height: 34px !important;
        }

        /* --- INPUTS E FORMULÁRIOS --- */
        [data-baseweb="input"], 
        [data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border: 1px solid #e4e4e7 !important;
            border-radius: 6px !important;
        }
        [data-baseweb="input"]:focus-within, 
        [data-baseweb="select"] > div:focus-within {
            border-color: #5b5bf6 !important;
        }
        input, .stSelectbox div {
            font-size: 14px !important;
            color: #3f3f46 !important;
        }

        /* Containers de card */
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px !important;
            border-color: #e4e4e7 !important;
            padding: 1rem !important;
        }
        
        hr {
            margin: 0.75rem 0 !important;
            border-color: #f4f4f5 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_session_state():
    defaults = {
        "reg_page": 1,
        "reg_busca": "",
        "filtro_mun": "Todos",
        "filtro_vacina": "Todas",
        "filtro_periodo": "2024",
        "filtro_idade": "Todas",
        "dados_municipios": [],
        "dados_vacinas": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def carregar_dados_apoio(token: str):
    """Carrega municípios e vacinas para preencher os dropdowns (apenas uma vez)."""
    if not st.session_state["dados_municipios"]:
        try:
            muns = listar_municipios(token, page_size=1000).get("items", [])
            st.session_state["dados_municipios"] = muns
        except ApiError:
            pass
    if not st.session_state["dados_vacinas"]:
        try:
            vacs = listar_vacinas(token, page_size=1000).get("items", [])
            st.session_state["dados_vacinas"] = vacs
        except ApiError:
            pass


def render_registros_section():
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado.")
        return

    _init_session_state()
    _inject_styles()
    carregar_dados_apoio(token)

    # 1. Cabeçalho
    col_title, col_space, col_csv, col_pdf = st.columns([5, 1, 1.5, 1.5])
    with col_title:
        st.markdown('<div class="page-title">Registros de vacinação</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-subtitle">Cadastre, edite e consulte registros individuais de vacinação</div>', unsafe_allow_html=True)
    with col_csv:
        st.button("Exportar CSV", use_container_width=True, key="registros_exportar_csv")
    with col_pdf:
        st.button("Exportar PDF", type="primary", use_container_width=True, key="registros_exportar_pdf")

    # 2. Card: Novo Registro
    _render_formulario(token)

    # 3. Filtros Livres (Fora do card, iguais ao design)
    _render_filtros()

    # 4. Card: Tabela de Registros
    _render_lista(token)


def _render_formulario(token: str):
    with st.container(border=True):
        st.markdown('<div class="registros-card-title">Novo registro</div>', unsafe_allow_html=True)

        # Preparando opções para os Selects
        opcoes_mun = [f"{m['nome']} ({m['id_ibge']})" for m in st.session_state["dados_municipios"]]
        opcoes_vac = [f"{v['nome']} (ID: {v['id']})" for m in st.session_state["dados_vacinas"] for v in [m]]

        with st.form("form_novo_registro", border=False, clear_on_submit=True):
            # Layout em linha exato do protótipo
            col_mun, col_vac, col_data, col_status, col_btn = st.columns([3, 3, 2.5, 2.5, 1.5])
            
            with col_mun:
                mun_selecionado = st.selectbox("Município", ["Selecione..."] + opcoes_mun, label_visibility="collapsed")
            with col_vac:
                vac_selecionada = st.selectbox("Vacina", ["Selecione..."] + opcoes_vac, label_visibility="collapsed")
            with col_data:
                data_vacina = st.date_input("Data", value=date.today(), format="DD/MM/YYYY", label_visibility="collapsed")
            with col_status:
                status_dado = st.selectbox("Status", ["Status: Válido", "Status: Inconsistente", "Status: Indeterminado"], label_visibility="collapsed")
            with col_btn:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)

        if salvar:
            if mun_selecionado == "Selecione..." or vac_selecionada == "Selecione...":
                st.error("Selecione o Município e a Vacina.")
                return
            
            # Extrair IDs das strings do selectbox
            id_ibge = mun_selecionado.split("(")[-1].replace(")", "")
            id_vacina = int(vac_selecionada.split("ID: ")[-1].replace(")", ""))
            
            mapa_status = {
                "Status: Válido": "VALIDO",
                "Status: Inconsistente": "DADO_INCONSISTENTE",
                "Status: Indeterminado": "DESLOCAMENTO_INDETERMINADO"
            }

            payload = {
                "data_vacinacao": data_vacina.isoformat(),
                "municipio_vacina_id": id_ibge,
                "vacina_id": id_vacina,
                "status_dado": mapa_status[status_dado],
                "quantidade": 1
            }

            try:
                criar_registro(token, payload)
                st.toast("Registro cadastrado com sucesso!")
                st.rerun()
            except ApiError as exc:
                st.error(exc.message)

def _render_filtros():
    # Margem inferior para afastar da tabela
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.selectbox("Município: todos", ["Município: todos", "Fortaleza", "Sobral"], label_visibility="collapsed")
    with col2:
        st.selectbox("Vacina: todas", ["Vacina: todas", "Antitetano", "Herpes-zóster", "Febre amarela"], label_visibility="collapsed")
    with col3:
        st.selectbox("Período: 2024", ["Período: 2024", "Período: 2023"], label_visibility="collapsed")
    with col4:
        st.selectbox("Faixa etária: todas", ["Faixa etária: todas", "0-10 anos", "11-20 anos"], label_visibility="collapsed")


def _render_lista(token: str):
    with st.container(border=True):
        col_title, col_busca = st.columns([2, 1])
        col_title.markdown('<div class="registros-card-title" style="margin-top: 6px;">Registros cadastrados</div>', unsafe_allow_html=True)
        
        with col_busca:
            busca = st.text_input("Buscar", value=st.session_state["reg_busca"], placeholder="Buscar município ou vacina", label_visibility="collapsed")
            if busca != st.session_state["reg_busca"]:
                st.session_state["reg_busca"] = busca
                st.session_state["reg_page"] = 1

        try:
            resultado = listar_registros(token, search=busca, page=st.session_state["reg_page"], page_size=5)
        except ApiError as exc:
            st.error(f"Erro ao carregar registros: {exc.message}")
            return

        itens = resultado.get("items", [])

        # Cabeçalho da Tabela
        st.markdown("<hr>", unsafe_allow_html=True)
        h1, h2, h3, h4, h5 = st.columns([1.5, 2.5, 2.5, 2.5, 2])
        h1.caption("**Data**")
        h2.caption("**Município**")
        h3.caption("**Vacina**")
        h4.caption("**Status**")
        h5.caption("**Ações**")
        st.markdown("<hr>", unsafe_allow_html=True)

        # Mapeamento visual exato da imagem
        mapa_badges = {
            "VALIDO": ("Válido", "success"),
            "DADO_INCONSISTENTE": ("Inconsistente", "warning"),
            "DESLOCAMENTO_INDETERMINADO": ("Deslocamento indeterminado", "neutral")
        }

        if not itens:
            st.info("Nenhum registro encontrado.")
        else:
            for reg in itens:
                linha = st.columns([1.5, 2.5, 2.5, 2.5, 2])
                
                # Data Formatada
                dt_obj = date.fromisoformat(reg["data_vacinacao"]) if reg.get("data_vacinacao") else None
                dt_str = dt_obj.strftime("%d/%m/%Y") if dt_obj else "-"
                linha[0].markdown(f"<span style='font-size:13px;color:#3f3f46;'>{dt_str}</span>", unsafe_allow_html=True)
                
                # Município (Se vazio, coloca o traço como na imagem)
                mun_nome = reg.get("municipio_vacina_nome") or "—"
                linha[1].markdown(f"<span style='font-size:13px;color:#3f3f46;'>{mun_nome}</span>", unsafe_allow_html=True)
                
                # Vacina
                vac_nome = reg.get("vacina_nome") or f"ID {reg.get('vacina_id', '-')}"
                linha[2].markdown(f"<span style='font-size:13px;color:#3f3f46;'>{vac_nome}</span>", unsafe_allow_html=True)
                
                # Badge de Status
                status_raw = reg.get("status_dado", "VALIDO")
                label, tone = mapa_badges.get(status_raw, ("Desconhecido", "neutral"))
                linha[3].markdown(_badge_html(label, tone), unsafe_allow_html=True)
                
                # Ações (Como texto/links discretos iguais ao Figma)
                with linha[4]:
                    acao_col1, acao_col2 = st.columns(2)
                    acao_col1.button("Editar", key=f"ed_{reg['id']}", use_container_width=True)
                    acao_col2.button("Desativar", key=f"del_{reg['id']}", use_container_width=True)
                
                st.markdown("<hr>", unsafe_allow_html=True)

        # Paginação
        total = resultado.get("total", 0)
        page = resultado.get("page", 1)
        total_pages = max(resultado.get("total_pages", 1), 1)

        c_info, c_space, c_prev, c_next = st.columns([6, 3, 0.5, 0.5])
        c_info.caption(f"Mostrando {len(itens)} de {total} registros")
        
        if c_prev.button("\<", disabled=page <= 1, key="prev_reg", use_container_width=True):
            st.session_state["reg_page"] = page - 1
            st.rerun()
        if c_next.button("\>", disabled=page >= total_pages, key="next_reg", use_container_width=True):
            st.session_state["reg_page"] = page + 1
            st.rerun()

if __name__ == "__main__":
    render_registros_section()