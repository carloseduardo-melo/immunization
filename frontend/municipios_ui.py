import streamlit as st

from api_client import ApiError, listar_municipios

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
]

STATUS_OPCOES = {"Todos": None, "Ativos": True, "Inativos": False}


def _init_session_state():
    defaults = {
        "municipios_page": 1,
        "municipios_uf": "Todas",
        "municipios_status": "Todos",
        "municipios_busca": "",
        "municipio_editando": None,
        "municipio_confirmando_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_municipios_section():
    _init_session_state()
    token = st.session_state["token"]
    pode_editar = st.session_state["role"] in ("ADMIN", "GESTOR_ESTADUAL")

    st.title("Municípios")
    _render_lista(token, pode_editar)


def _render_lista(token: str, pode_editar: bool):
    st.subheader("Municípios cadastrados")

    col_busca, col_uf, col_status = st.columns([2, 1, 1])
    with col_busca:
        busca = st.text_input("Buscar município", value=st.session_state["municipios_busca"])
    with col_uf:
        opcoes_uf = ["Todas"] + UFS
        uf = st.selectbox("UF", opcoes_uf, index=opcoes_uf.index(st.session_state["municipios_uf"]))
    with col_status:
        opcoes_status = list(STATUS_OPCOES.keys())
        status_label = st.selectbox(
            "Situação", opcoes_status, index=opcoes_status.index(st.session_state["municipios_status"])
        )

    if (busca != st.session_state["municipios_busca"]
            or uf != st.session_state["municipios_uf"]
            or status_label != st.session_state["municipios_status"]):
        st.session_state["municipios_busca"] = busca
        st.session_state["municipios_uf"] = uf
        st.session_state["municipios_status"] = status_label
        st.session_state["municipios_page"] = 1

    try:
        with st.spinner("Carregando municípios..."):
            resultado = listar_municipios(
                token,
                uf="" if uf == "Todas" else uf,
                ativo=STATUS_OPCOES[status_label],
                search=busca,
                page=st.session_state["municipios_page"],
                page_size=10,
            )
    except ApiError as exc:
        st.error(exc.message)
        return

    itens = resultado["items"]

    if not itens:
        st.info("Nenhum município encontrado para os filtros selecionados.")
        return

    header = st.columns([3, 3, 2, 2])
    header[0].markdown("**Município**")
    header[1].markdown("**Região de saúde**")
    header[2].markdown("**Tipo**")
    header[3].markdown("**Ações**")

    for municipio in itens:
        linha = st.columns([3, 3, 2, 2])
        nome_exibido = municipio["nome"] if municipio["ativo"] else f"{municipio['nome']} (inativo)"
        linha[0].write(nome_exibido)
        linha[1].write(municipio.get("regiao_saude") or "-")
        linha[2].write("Polo" if municipio["polo"] else "Padrão")

        if pode_editar:
            with linha[3]:
                acao_col1, acao_col2 = st.columns(2)
                if acao_col1.button("Editar", key=f"editar_{municipio['id_ibge']}"):
                    st.session_state["municipio_editando"] = municipio
                    st.rerun()
                if municipio["ativo"] and acao_col2.button("Desativar", key=f"desativar_{municipio['id_ibge']}"):
                    st.session_state["municipio_confirmando_id"] = municipio["id_ibge"]
                    st.rerun()
        else:
            linha[3].write("-")

    total = resultado["total"]
    page = resultado["page"]
    total_pages = max(resultado["total_pages"], 1)

    st.caption(f"Mostrando {len(itens)} de {total} municípios")

    col_prev, col_info, col_next = st.columns([1, 2, 1])
    if col_prev.button("Anterior", disabled=page <= 1):
        st.session_state["municipios_page"] = page - 1
        st.rerun()
    col_info.write(f"Página {page} de {total_pages}")
    if col_next.button("Próxima", disabled=page >= total_pages):
        st.session_state["municipios_page"] = page + 1
        st.rerun()
