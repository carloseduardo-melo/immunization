from typing import Optional

import streamlit as st

from api_client import ApiError, atualizar_municipio, criar_municipio, desativar_municipio, listar_municipios

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

    if pode_editar:
        _render_formulario(token)
        st.divider()

    _render_lista(token, pode_editar)


def _validar_formulario(id_ibge: str, nome: str, uf: str, editando: Optional[dict]) -> Optional[str]:
    if not editando and (not id_ibge or not id_ibge.isdigit() or len(id_ibge) != 7):
        return "Informe um código IBGE válido com 7 dígitos."
    if not nome or not nome.strip():
        return "Informe o nome do município."
    if not uf or len(uf.strip()) != 2 or not uf.strip().isalpha():
        return "Informe a UF com exatamente 2 letras."
    return None


def _render_formulario(token: str):
    editando = st.session_state["municipio_editando"]
    titulo = "Editar município" if editando else "Novo município"
    st.subheader(titulo)

    with st.form("form_municipio", clear_on_submit=False):
        id_ibge = st.text_input(
            "Código IBGE",
            value=editando["id_ibge"] if editando else "",
            disabled=bool(editando),
            max_chars=7,
        )
        nome = st.text_input("Nome do município", value=editando["nome"] if editando else "")
        uf = st.text_input("UF", value=editando["uf"] if editando else "", max_chars=2)
        regiao_saude = st.text_input(
            "Região de saúde",
            value=(editando.get("regiao_saude") or "") if editando else "",
        )
        polo = st.checkbox("Município-polo", value=editando["polo"] if editando else False)

        col_salvar, col_cancelar = st.columns(2)
        salvar = col_salvar.form_submit_button("Salvar")
        cancelar = col_cancelar.form_submit_button("Cancelar edição", disabled=not editando)

    if cancelar:
        st.session_state["municipio_editando"] = None
        st.rerun()

    if salvar:
        erro = _validar_formulario(id_ibge, nome, uf, editando)
        if erro:
            st.error(erro)
            return

        payload = {
            "nome": nome.strip(),
            "uf": uf.strip().upper(),
            "regiao_saude": regiao_saude.strip() or None,
            "polo": polo,
        }

        try:
            if editando:
                atualizar_municipio(token, editando["id_ibge"], payload)
                st.success("Município atualizado com sucesso.")
            else:
                payload["id_ibge"] = id_ibge.strip()
                criar_municipio(token, payload)
                st.success("Município cadastrado com sucesso.")
            st.session_state["municipio_editando"] = None
            st.rerun()
        except ApiError as exc:
            st.error(exc.message)


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

    if pode_editar and st.session_state["municipio_confirmando_id"]:
        _render_confirmacao_desativacao(token, st.session_state["municipio_confirmando_id"])


def confirmar_desativacao(token: str, id_ibge: str) -> None:
    try:
        desativar_municipio(token, id_ibge)
        st.session_state["municipio_confirmando_id"] = None
        st.success("Município desativado com sucesso.")
    except ApiError as exc:
        st.error(exc.message)


# Compatibilidade: `st.dialog` só existe a partir do Streamlit 1.37;
# a versão fixada em requirements.txt (1.36.0) expõe apenas `st.experimental_dialog`.
_dialog = getattr(st, "dialog", None) or st.experimental_dialog


@_dialog("Desativar município")
def _render_confirmacao_desativacao(token: str, id_ibge: str):
    st.write("Deseja realmente desativar este município?")
    st.caption("O município não será excluído do banco de dados, apenas ficará inativo.")

    col_cancelar, col_confirmar = st.columns(2)
    if col_cancelar.button("Cancelar"):
        st.session_state["municipio_confirmando_id"] = None
        st.rerun()
    if col_confirmar.button("Desativar", type="primary"):
        confirmar_desativacao(token, id_ibge)
        st.rerun()
