from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from api_client import ApiError, listar_registros, listar_vacinas


def _badge_html(label: str, tone: str) -> str:
    tones = {
        "success": ("#dcfce7", "#15803d"),
        "warning": ("#fef3c7", "#b45309"),
        "danger": ("#fee2e2", "#b91c1c"),
        "info": ("#e0f2fe", "#0369a1"),
    }
    bg, color = tones.get(tone, ("#f4f4f5", "#52525b"))
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'font-size:12px;font-weight:500;background:{bg};color:{color};">{label}</span>'
    )


def render_registros_section():
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar os registros.")
        return

    st.markdown('<div class="page-title">💉 Registros de Vacinação</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Consulta consolidada dos registros de vacinação, deslocamento e completude de dados.</div>',
        unsafe_allow_html=True,
    )

    # Estado dos Filtros no Streamlit Session State
    if "reg_page" not in st.session_state:
        st.session_state["reg_page"] = 1
    if "reg_municipio" not in st.session_state:
        st.session_state["reg_municipio"] = ""
    if "reg_vacina_id" not in st.session_state:
        st.session_state["reg_vacina_id"] = None
    if "reg_data_inicio" not in st.session_state:
        st.session_state["reg_data_inicio"] = None
    if "reg_data_fim" not in st.session_state:
        st.session_state["reg_data_fim"] = None
    if "reg_idade_min" not in st.session_state:
        st.session_state["reg_idade_min"] = None
    if "reg_idade_max" not in st.session_state:
        st.session_state["reg_idade_max"] = None
    if "reg_status" not in st.session_state:
        st.session_state["reg_status"] = ""

    # Painel de Filtros (Expander)
    with st.expander("🔍 Filtros de Pesquisa", expanded=True):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])

        with col1:
            municipio_input = st.text_input(
                "Código IBGE Município",
                value=st.session_state["reg_municipio"],
                placeholder="Ex: 2304400",
                help="Filtra por município de aplicação ou residência",
            )

        with col2:
            data_ini = st.date_input(
                "Data Inicial",
                value=st.session_state["reg_data_inicio"],
                format="DD/MM/YYYY",
            )
            data_fim = st.date_input(
                "Data Final",
                value=st.session_state["reg_data_fim"],
                format="DD/MM/YYYY",
            )

        with col3:
            idade_min_val = st.number_input(
                "Idade Mínima",
                min_value=0,
                max_value=120,
                value=st.session_state["reg_idade_min"],
                step=1,
            )
            idade_max_val = st.number_input(
                "Idade Máxima",
                min_value=0,
                max_value=120,
                value=st.session_state["reg_idade_max"],
                step=1,
            )

        with col4:
            status_options = ["Todos", "VALIDO", "DADO_INCONSISTENTE", "DESLOCAMENTO_INDETERMINADO"]
            current_status = st.session_state["reg_status"] or "Todos"
            status_idx = status_options.index(current_status) if current_status in status_options else 0
            status_sel = st.selectbox("Status do Dado", options=status_options, index=status_idx)

        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
        with col_btn1:
            if st.button("Filtrar", use_container_width=True, type="primary"):
                st.session_state["reg_municipio"] = municipio_input.strip()
                st.session_state["reg_data_inicio"] = data_ini
                st.session_state["reg_data_fim"] = data_fim
                st.session_state["reg_idade_min"] = idade_min_val
                st.session_state["reg_idade_max"] = idade_max_val
                st.session_state["reg_status"] = "" if status_sel == "Todos" else status_sel
                st.session_state["reg_page"] = 1
                st.rerun()

        with col_btn2:
            if st.button("Limpar Filtros", use_container_width=True):
                st.session_state["reg_municipio"] = ""
                st.session_state["reg_vacina_id"] = None
                st.session_state["reg_data_inicio"] = None
                st.session_state["reg_data_fim"] = None
                st.session_state["reg_idade_min"] = None
                st.session_state["reg_idade_max"] = None
                st.session_state["reg_status"] = ""
                st.session_state["reg_page"] = 1
                st.rerun()

    # Consulta dos Registros na API Backend
    try:
        data_ini_str = st.session_state["reg_data_inicio"].isoformat() if st.session_state["reg_data_inicio"] else ""
        data_fim_str = st.session_state["reg_data_fim"].isoformat() if st.session_state["reg_data_fim"] else ""

        resultado = listar_registros(
            token=token,
            municipio_id=st.session_state["reg_municipio"],
            vacina_id=st.session_state["reg_vacina_id"],
            data_inicio=data_ini_str,
            data_fim=data_fim_str,
            idade_min=st.session_state["reg_idade_min"],
            idade_max=st.session_state["reg_idade_max"],
            status_dado=st.session_state["reg_status"],
            page=st.session_state["reg_page"],
            page_size=10,
        )
    except ApiError as err:
        st.error(f"Erro ao carregar registros de vacinação: {err.message}")
        return

    items = resultado.get("items", [])
    total = resultado.get("total", 0)
    page = resultado.get("page", 1)
    total_pages = resultado.get("total_pages", 0)

    # Exibição de Métricas
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("Total de Registros Encontrados", f"{total:,}".replace(",", "."))
    m_col2.metric("Página Atual", f"{page} de {total_pages}" if total_pages > 0 else "0 de 0")
    m_col3.metric("Registros Exibidos", len(items))

    st.markdown("---")

    if not items:
        st.info("Nenhum registro de vacinação encontrado para os filtros selecionados.")
        return

    # Formatação da Tabela
    rows = []
    for item in items:
        # Formata data
        dt_str = item.get("data_vacinacao")
        if dt_str:
            try:
                dt_obj = date.fromisoformat(dt_str)
                dt_formatted = dt_obj.strftime("%d/%m/%Y")
            except Exception:
                dt_formatted = dt_str
        else:
            dt_formatted = "-"

        # Formata município vacina
        mun_vac_id = item.get("municipio_vacina_id") or ""
        mun_vac_nome = item.get("municipio_vacina_nome") or ""
        mun_vac_str = f"{mun_vac_nome} ({mun_vac_id})" if mun_vac_nome else mun_vac_id

        # Formata município residência
        mun_res_id = item.get("municipio_residencia_id") or ""
        mun_res_nome = item.get("municipio_residencia_nome") or ""
        mun_res_str = f"{mun_res_nome} ({mun_res_id})" if mun_res_nome else (mun_res_id if mun_res_id else "Não Informado")

        # Deslocamento
        desloc = item.get("teve_deslocamento")
        if desloc is True:
            desloc_str = "Sim 🚗"
        elif desloc is False:
            desloc_str = "Não 🏠"
        else:
            desloc_str = "Indeterminado ❓"

        rows.append(
            {
                "Data Vacinação": dt_formatted,
                "Vacina": item.get("vacina_nome") or f"ID #{item.get('vacina_id')}",
                "Idade": item.get("idade") if item.get("idade") is not None else "-",
                "Município Aplicação": mun_vac_str,
                "Município Residência": mun_res_str,
                "Deslocamento": desloc_str,
                "Quantidade": item.get("quantidade", 1),
                "Status Dado": item.get("status_dado", "VALIDO"),
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Paginação
    p_col1, p_col2, p_col3, _ = st.columns([1, 1, 2, 4])
    with p_col1:
        if st.button("⬅️ Anterior", disabled=(page <= 1), use_container_width=True):
            st.session_state["reg_page"] = max(1, page - 1)
            st.rerun()

    with p_col2:
        if st.button("Próxima ➡️", disabled=(page >= total_pages), use_container_width=True):
            st.session_state["reg_page"] = page + 1
            st.rerun()

    with p_col3:
        st.write(f"Página **{page}** de **{total_pages}**")
