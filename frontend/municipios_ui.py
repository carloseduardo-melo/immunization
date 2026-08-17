import random
from typing import Any, Optional

import streamlit as st

from api_client import (
    ApiError,
    atualizar_municipio,
    atualizar_vacina,
    criar_municipio,
    criar_vacina,
    desativar_municipio,
    desativar_vacina,
    listar_municipios,
    listar_vacinas,
)
from theme import badge_html as _badge_html


def _init_session_state():
    defaults = {
        "token": "token_dummy",
        "role": "ADMIN",
        # Municípios
        "municipios_page": 1,
        "municipios_busca": "",
        "municipio_editando": None,
        "municipio_confirmando_id": None,
        "municipio_dialog_shown": False,
        # Vacinas (RF04 & RF05)
        "vacinas_page": 1,
        "vacinas_busca": "",
        "vacina_editando": None,
        "vacina_confirmando_id": None,
        "vacina_dialog_shown": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def render_municipios_section():
    _init_session_state()
    token = st.session_state.get("token", "")
    role = st.session_state.get("role", "")
    pode_editar = role in ("ADMIN", "GESTOR_ESTADUAL")
    is_admin = role == "ADMIN"

    # Cabeçalho da Página
    col_title, col_space, col_csv, col_pdf = st.columns([6, 1, 1.5, 1.5])
    with col_title:
        st.markdown('<div class="page-title">Cadastro de município e vacina</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-subtitle">Administração do catálogo de municípios e imunobiológicos</div>', unsafe_allow_html=True)
    with col_csv:
        st.button("Exportar CSV", use_container_width=True, key="municipios_exportar_csv")
    with col_pdf:
        st.button("Exportar PDF", type="primary", use_container_width=True, key="municipios_exportar_pdf")

    # --- SEÇÃO DE MUNICÍPIOS ---
    if pode_editar:
        _render_formulario_municipio(token)
    _render_lista_municipios(token, pode_editar)

    # --- SEÇÃO DE VACINAS (RF04 & RF05) ---
    if pode_editar:
        _render_formulario_vacina(token, is_admin)
    _render_lista_vacinas(token, pode_editar)


# ==========================================
# MUNICÍPIOS
# ==========================================

def _render_formulario_municipio(token: str):
    editando = st.session_state["municipio_editando"]
    titulo = "Editar município" if editando else "Novo município"

    with st.container(border=True):
        st.markdown(f'<div class="card-title">{titulo}</div>', unsafe_allow_html=True)

        with st.form("form_municipio", border=False, clear_on_submit=True):
            col_nome, col_regiao, col_polo, col_salvar, col_cancel = st.columns([4, 3, 2, 1.5, 1.5] if editando else [4.5, 3.5, 2, 2, 0.1])
            
            with col_nome:
                nome = st.text_input("Nome", value=editando["nome"] if editando else "", placeholder="Nome do município", label_visibility="collapsed")
            
            with col_regiao:
                opcoes_regiao = ["", "Região de Fortaleza", "Região Norte", "Região do Cariri", "Região do Sertão Central"]
                val_atual = editando.get("regiao_saude") if editando else ""
                idx = opcoes_regiao.index(val_atual) if val_atual in opcoes_regiao else 0
                regiao_saude = st.selectbox("Região", opcoes_regiao, index=idx, label_visibility="collapsed", placeholder="Região de saúde")
            
            with col_polo:
                polo = st.checkbox("Município-polo", value=editando["polo"] if editando else False)
            
            with col_salvar:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)
                
            if editando:
                with col_cancel:
                    if st.form_submit_button("Cancelar", use_container_width=True):
                        st.session_state["municipio_editando"] = None
                        st.rerun()

        if salvar:
            if not nome or not nome.strip():
                st.error("Informe o nome do município.")
                return

            payload = {
                "nome": nome.strip(),
                "uf": editando["uf"] if editando else "CE",
                "regiao_saude": regiao_saude.strip() or None,
                "polo": polo,
            }

            try:
                if editando:
                    atualizar_municipio(token, editando["id_ibge"], payload)
                    st.toast("Município atualizado com sucesso.")
                else:
                    payload["id_ibge"] = str(random.randint(1000000, 9999999))
                    criar_municipio(token, payload)
                    st.toast("Município cadastrado com sucesso.")
                st.session_state["municipio_editando"] = None
                st.rerun()
            except ApiError as exc:
                st.error(exc.message)


def _render_lista_municipios(token: str, pode_editar: bool):
    with st.container(border=True):
        col_titulo, col_space, col_busca = st.columns([3, 4, 3])
        col_titulo.markdown('<div class="card-title" style="margin-top: 6px;">Municípios cadastrados</div>', unsafe_allow_html=True)
        
        with col_busca:
            busca = st.text_input("Buscar", value=st.session_state["municipios_busca"], placeholder="Buscar município", label_visibility="collapsed", key="input_busca_mun")

        if busca != st.session_state["municipios_busca"]:
            st.session_state["municipios_busca"] = busca
            st.session_state["municipios_page"] = 1
            st.rerun()

        try:
            with st.spinner("Carregando municípios..."):
                resultado = listar_municipios(
                    token,
                    uf="",
                    ativo=None,
                    search=busca,
                    page=st.session_state["municipios_page"],
                    page_size=3,
                )
        except ApiError as exc:
            st.error(exc.message)
            return

        itens = resultado.get("items", [])

        if not itens:
            st.info("Nenhum município encontrado.")
            return

        st.markdown("<hr>", unsafe_allow_html=True)
        h1, h2, h3, h4 = st.columns([3.2, 3.2, 1.4, 2.7])
        h1.caption("**Município**")
        h2.caption("**Região de saúde**")
        h3.caption("**Tipo**")
        h4.caption("**Ações**")
        st.markdown("<hr>", unsafe_allow_html=True)

        for municipio in itens:
            linha = st.columns([3.2, 3.2, 1.4, 2.7])
            nome_html = municipio["nome"]
            if not municipio.get("ativo", True):
                nome_html += " " + _badge_html("Inativo", "neutral")
            
            linha[0].markdown(f"<span style='font-size:13px;color:#3f3f46;'>{nome_html}</span>", unsafe_allow_html=True)
            linha[1].markdown(f"<span style='font-size:13px;color:#71717a;'>{municipio.get('regiao_saude') or '-'}</span>", unsafe_allow_html=True)
            
            tipo_badge = _badge_html("Polo", "success") if municipio.get("polo") else _badge_html("Padrão", "neutral")
            linha[2].markdown(tipo_badge, unsafe_allow_html=True)

            if pode_editar:
                with linha[3]:
                    acao_col1, acao_col2 = st.columns(2)
                    if acao_col1.button("Editar", key=f"editar_{municipio['id_ibge']}", use_container_width=True):
                        st.session_state["municipio_editando"] = municipio
                        st.rerun()
                    if municipio.get("ativo", True) and acao_col2.button("Desativar", key=f"desativar_{municipio['id_ibge']}", use_container_width=True):
                        st.session_state["municipio_confirmando_id"] = municipio["id_ibge"]
                        st.session_state["municipio_dialog_shown"] = False
                        st.rerun()
            else:
                linha[3].write("-")
            
            st.markdown("<hr>", unsafe_allow_html=True)

        total = resultado.get("total", len(itens))
        page = resultado.get("page", 1)
        total_pages = max(resultado.get("total_pages", 1), 1)

        c_info, c_space, c_prev, c_next = st.columns([6, 3, 0.5, 0.5])
        c_info.caption(f"Mostrando {len(itens)} de {total} municípios")
        
        if c_prev.button("<", disabled=page <= 1, key="prev_mun", use_container_width=True):
            st.session_state["municipios_page"] = page - 1
            st.rerun()
        if c_next.button(">", disabled=page >= total_pages, key="next_mun", use_container_width=True):
            st.session_state["municipios_page"] = page + 1
            st.rerun()

        if pode_editar and st.session_state["municipio_confirmando_id"] and not st.session_state["municipio_dialog_shown"]:
            st.session_state["municipio_dialog_shown"] = True
            _render_confirmacao_desativacao(token, st.session_state["municipio_confirmando_id"])


# ==========================================
# VACINAS (RF04 & RF05)
# ==========================================

def _render_formulario_vacina(token: str, is_admin: bool):
    editando = st.session_state["vacina_editando"]
    titulo = "Editar vacina" if editando else "Nova vacina"

    with st.container(border=True):
        st.markdown(f'<div class="card-title">{titulo}</div>', unsafe_allow_html=True)

        with st.form("form_vacina", border=False, clear_on_submit=True):
            col_nome, col_complex, col_salvar, col_cancel = st.columns([6, 3, 1.5, 1.5] if editando else [6, 3, 2, 0.1])
            
            with col_nome:
                nome = st.text_input(
                    "Nome",
                    value=editando["nome"] if editando else "",
                    placeholder="Nome da vacina",
                    label_visibility="collapsed",
                )
            with col_complex:
                # Regra RF05: Marcar/desmarcar alta complexidade só é permitido para Administrador
                val_complex = editando.get("alta_complexidade", False) if editando else False
                alta_complex = st.checkbox(
                    "Alta complexidade",
                    value=val_complex,
                    disabled=not is_admin,
                    help="Permitido apenas para perfil Administrador" if not is_admin else None,
                )
            with col_salvar:
                salvar = st.form_submit_button("Salvar", type="primary", use_container_width=True)
            
            if editando:
                with col_cancel:
                    if st.form_submit_button("Cancelar", use_container_width=True):
                        st.session_state["vacina_editando"] = None
                        st.rerun()

        if salvar:
            if not nome or not nome.strip():
                st.error("Informe o nome da vacina.")
                return
            
            payload = {
                "nome": nome.strip(),
                "alta_complexidade": alta_complex,
            }

            try:
                if editando:
                    atualizar_vacina(token, editando["id"], payload)
                    st.toast("Vacina atualizada com sucesso.")
                else:
                    criar_vacina(token, payload)
                    st.toast("Vacina cadastrada com sucesso.")
                st.session_state["vacina_editando"] = None
                st.rerun()
            except ApiError as exc:
                st.error(exc.message)


def _render_lista_vacinas(token: str, pode_editar: bool):
    with st.container(border=True):
        col_titulo, col_space, col_busca = st.columns([3, 4, 3])
        col_titulo.markdown('<div class="card-title" style="margin-top: 6px;">Vacinas cadastradas</div>', unsafe_allow_html=True)
        
        with col_busca:
            busca = st.text_input(
                "Buscar",
                value=st.session_state["vacinas_busca"],
                placeholder="Buscar vacina",
                label_visibility="collapsed",
                key="input_busca_vac",
            )
            if busca != st.session_state["vacinas_busca"]:
                st.session_state["vacinas_busca"] = busca
                st.session_state["vacinas_page"] = 1
                st.rerun()

        try:
            with st.spinner("Carregando vacinas..."):
                resultado = listar_vacinas(
                    token,
                    search=busca,
                    page=st.session_state["vacinas_page"],
                    page_size=3,
                )
        except ApiError as exc:
            st.error(exc.message)
            return

        itens = resultado.get("items", [])

        if not itens:
            st.info("Nenhuma vacina encontrada.")
            return

        st.markdown("<hr>", unsafe_allow_html=True)
        h1, h2, h3 = st.columns([4.3, 2.9, 2.8])
        h1.caption("**Nome**")
        h2.caption("**Complexidade**")
        h3.caption("**Ações**")
        st.markdown("<hr>", unsafe_allow_html=True)

        for vacina in itens:
            linha = st.columns([4.3, 2.9, 2.8])
            nome_html = vacina["nome"]
            if not vacina.get("ativo", True):
                nome_html += " " + _badge_html("Inativo", "neutral")

            linha[0].markdown(f"<span style='font-size:13px;color:#3f3f46;'>{nome_html}</span>", unsafe_allow_html=True)
            
            is_alta = vacina.get("alta_complexidade", False)
            complex_badge = _badge_html("Alta", "alta") if is_alta else _badge_html("Padrão", "neutral")
            linha[1].markdown(complex_badge, unsafe_allow_html=True)

            if pode_editar:
                with linha[2]:
                    acao_col1, acao_col2 = st.columns(2)
                    if acao_col1.button("Editar", key=f"editar_vac_{vacina['id']}", use_container_width=True):
                        st.session_state["vacina_editando"] = vacina
                        st.rerun()
                    if vacina.get("ativo", True) and acao_col2.button("Desativar", key=f"desativar_vac_{vacina['id']}", use_container_width=True):
                        st.session_state["vacina_confirmando_id"] = vacina["id"]
                        st.session_state["vacina_dialog_shown"] = False
                        st.rerun()
            else:
                linha[2].write("-")
            
            st.markdown("<hr>", unsafe_allow_html=True)

        total = resultado.get("total", len(itens))
        page = resultado.get("page", 1)
        total_pages = max(resultado.get("total_pages", 1), 1)

        c_info, c_space, c_prev, c_next = st.columns([6, 3, 0.5, 0.5])
        c_info.caption(f"Mostrando {len(itens)} de {total} vacinas")
        if c_prev.button("<", key="prev_vac", disabled=page <= 1, use_container_width=True):
            st.session_state["vacinas_page"] = page - 1
            st.rerun()
        if c_next.button(">", key="next_vac", disabled=page >= total_pages, use_container_width=True):
            st.session_state["vacinas_page"] = page + 1
            st.rerun()

        if pode_editar and st.session_state["vacina_confirmando_id"] and not st.session_state["vacina_dialog_shown"]:
            st.session_state["vacina_dialog_shown"] = True
            _render_confirmacao_desativacao_vacina(token, st.session_state["vacina_confirmando_id"])


# ==========================================
# MODAIS / DIÁLOGOS DE CONFIRMAÇÃO
# ==========================================

_dialog = getattr(st, "dialog", None) or st.experimental_dialog

@_dialog("Desativar município")
def _render_confirmacao_desativacao(token: str, id_ibge: str):
    st.write("Deseja realmente desativar este município?")
    st.caption("O município não será excluído do banco de dados, apenas ficará inativo.")

    col_cancelar, col_confirmar = st.columns(2)
    if col_cancelar.button("Cancelar", use_container_width=True):
        st.session_state["municipio_confirmando_id"] = None
        st.session_state["municipio_dialog_shown"] = False
        st.rerun()
    if col_confirmar.button("Desativar", type="primary", use_container_width=True):
        try:
            desativar_municipio(token, id_ibge)
            st.session_state["municipio_confirmando_id"] = None
            st.toast("Município desativado com sucesso.")
        except ApiError as exc:
            st.error(exc.message)
        st.session_state["municipio_dialog_shown"] = False
        st.rerun()


@_dialog("Desativar vacina")
def _render_confirmacao_desativacao_vacina(token: str, vacina_id: Any):
    st.write("Deseja realmente desativar esta vacina?")
    st.caption("A vacina não será excluída do banco de dados, apenas ficará com o status inativo.")

    col_cancelar, col_confirmar = st.columns(2)
    if col_cancelar.button("Cancelar", use_container_width=True):
        st.session_state["vacina_confirmando_id"] = None
        st.session_state["vacina_dialog_shown"] = False
        st.rerun()
    if col_confirmar.button("Desativar", type="primary", use_container_width=True):
        try:
            desativar_vacina(token, vacina_id)
            st.session_state["vacina_confirmando_id"] = None
            st.toast("Vacina desativada com sucesso.")
        except ApiError as exc:
            st.error(exc.message)
        st.session_state["vacina_dialog_shown"] = False
        st.rerun()


if __name__ == "__main__":
    render_municipios_section()
