import os
import streamlit as st
import requests

from streamlit_cookies_controller import CookieController

from api_client import ApiError, obter_me
from municipios_ui import render_municipios_section
from registros_ui import render_registros_section
from ui_dashboard import render_dashboard_section  # <-- IMPORTAÇÃO DO DASHBOARD
from theme import COLORS, inject_global_styles


# ============================================================
# CONFIGURAÇÕES
# ============================================================

API_URL = os.getenv(
    "BACKEND_URL",
    "http://localhost:8000"
)

st.set_page_config(
    page_title="Caminhos da Imunização",
    page_icon="💉",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_global_styles()

cookies = CookieController()


# ============================================================
# ESTADO DA SESSÃO
# ============================================================

if "token" not in st.session_state:
    st.session_state["token"] = None

if "role" not in st.session_state:
    st.session_state["role"] = None

if "municipio_id" not in st.session_state:
    st.session_state["municipio_id"] = None

if "_cookie_sync" not in st.session_state:
    st.session_state["_cookie_sync"] = None

if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "dashboard"  # <-- DASHBOARD COMO TELA INICIAL

# Sincroniza o cookie pendente de uma rodada anterior (login ou logout).
# Isso precisa acontecer numa rodada que NÃO termina em st.rerun() logo em
# seguida: o componente de cookie roda num iframe que só grava/remove o
# cookie depois de carregar e montar no navegador. Se um st.rerun() troca a
# árvore de elementos antes disso, o iframe é desmontado e o cookie nunca
# chega a ser gravado (foi o que causava o F5 sempre voltar pro login).
if st.session_state["_cookie_sync"] == "set":
    cookies.set("token", st.session_state["token"])
    st.session_state["_cookie_sync"] = None
elif st.session_state["_cookie_sync"] == "clear":
    if cookies.get("token") is not None:
        cookies.remove("token")
    st.session_state["_cookie_sync"] = None

# Recupera a sessão do cookie do navegador (ex.: após um F5).
# O componente de cookies carrega de forma assíncrona, então o valor
# real só chega em um rerun subsequente disparado automaticamente.
if not st.session_state["token"]:

    cookie_token = cookies.get("token")

    if cookie_token:
        try:
            me = obter_me(cookie_token)
        except ApiError:
            # Token expirado/inválido: limpa o cookie e mantém a tela de login.
            cookies.remove("token")
        else:
            st.session_state["token"] = cookie_token
            st.session_state["role"] = me.get("role")
            st.session_state["municipio_id"] = me.get("municipio_alocado_id")


# ============================================================
# TELA DE LOGIN
# ============================================================

if not st.session_state["token"]:

    # --------------------------------------------------------
    # CSS DA TELA DE LOGIN
    # --------------------------------------------------------

    st.markdown(
        f"""
        <style>
        /* Tela de login: layout split-screen full-bleed */

        /* 1. Reset estrutural */
        html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .stApp {{
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            min-height: 100vh !important;
            background: #ffffff !important;
        }}
        
        .main .block-container, [data-testid="stMainBlockContainer"] {{
            padding: 0 !important;
            margin: 0 !important;
            max-width: 100% !important;
            width: 100% !important;
        }}
        
        [data-testid="stHeader"], [data-testid="stSidebar"] {{
            display: none !important;
        }}

        /* 2. Container Pai (stHorizontalBlock) */
        [data-testid="stHorizontalBlock"] {{
            display: flex !important;
            flex-direction: row !important;
            width: 100vw !important;
            min-height: 100vh !important;
            margin: 0 !important;
            padding: 0 !important;
            gap: 0 !important;
            align-items: stretch !important;
        }}

        /* 3. Painel Esquerdo (Azul) - Seletor corrigido para "column" */
        [data-testid="column"]:nth-of-type(1) {{
            background-color: {COLORS["sidebar_bg"]} !important;
            min-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            padding: 0 10% !important;
            width: 50% !important;
            flex: 1 1 50% !important; /* Força metade da tela */
        }}

        [data-testid="column"]:nth-of-type(1) > div {{
            margin: auto 0 !important;
            max-width: 500px !important;
        }}

        /* 4. Painel Direito (Branco) */
        [data-testid="column"]:nth-of-type(2) {{
            background-color: #ffffff !important;
            min-height: 100vh !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            padding: 0 10% !important;
            width: 50% !important;
            flex: 1 1 50% !important;
        }}
        
        [data-testid="column"]:nth-of-type(2) > div {{
            margin: auto !important;
            width: 100% !important;
            max-width: 380px !important;
        }}

        /* 5. Tipografia e Elementos da Marca (Esquerda) */
        .logo-box {{
            width: 56px;
            height: 56px;
            background: #ffffff;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 28px;
        }}
        .logo-inner {{
            width: 20px;
            height: 20px;
            background: {COLORS["sidebar_bg"]};
            border-radius: 4px;
        }}
        .brand-title {{
            margin: 0 0 14px 0;
            color: #ffffff;
            font-size: 34px;
            line-height: 1.2;
            font-weight: 700;
            letter-spacing: -0.6px;
        }}
        .brand-description {{
            margin: 0;
            color: {COLORS["sidebar_text"]};
            font-size: 16px;
            line-height: 1.6;
            font-weight: 400;
        }}

        /* 6. Tipografia do Login (Direita) */
        .login-title {{
            margin: 0 0 8px 0;
            color: {COLORS["ink"]};
            font-size: 25px;
            line-height: 1.3;
            font-weight: 700;
            letter-spacing: -0.3px;
        }}
        .login-subtitle {{
            margin: 0 0 30px 0;
            color: {COLORS["muted"]};
            font-size: 14px;
            line-height: 1.5;
            font-weight: 400;
        }}

        /* 7. Estilização do Formulário */
        [data-testid="stForm"] {{
            border: none !important;
            padding: 0 !important;
            margin: 0 !important;
            background: transparent !important;
        }}
        [data-testid="stForm"] label p {{
            color: {COLORS["ink"]} !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            margin-bottom: 4px !important;
        }}
        [data-testid="stForm"] input {{
            height: 46px !important;
            min-height: 46px !important;
            border-radius: 8px !important;
            border: 1px solid {COLORS["border"]} !important;
            padding: 0 14px !important;
            font-size: 14px !important;
            background: #ffffff !important;
            color: {COLORS["ink"]} !important;
            box-shadow: none !important;
        }}
        [data-testid="stForm"] input:focus {{
            border-color: {COLORS["primary"]} !important;
            box-shadow: 0 0 0 1px {COLORS["primary"]} !important;
        }}
        
        /* 8. Botão de Submit */
        [data-testid="stFormSubmitButton"] {{
            width: 100% !important;
            margin-top: 16px !important;
        }}
        [data-testid="stFormSubmitButton"] button {{
            width: 100% !important;
            height: 46px !important;
            min-height: 46px !important;
            background-color: {COLORS["sidebar_bg"]} !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-size: 15px !important;
            font-weight: 600 !important;
            padding: 0 !important;
            transition: all 0.2s ease !important;
        }}
        [data-testid="stFormSubmitButton"] button:hover {{
            background-color: {COLORS["sidebar_bg_active"]} !important;
            color: #ffffff !important;
            opacity: 0.95;
        }}
        [data-testid="stFormSubmitButton"] button:active {{
            transform: translateY(1px);
        }}

        /* 9. Textos auxiliares */
        .forgot-pass {{
            margin-top: 24px;
            color: {COLORS["muted"]};
            font-size: 13px;
        }}

        /* 10. Responsividade para Mobile */
        @media (max-width: 768px) {{
            [data-testid="stHorizontalBlock"] {{
                flex-direction: column !important;
            }}
            [data-testid="column"]:nth-of-type(1), 
            [data-testid="column"]:nth-of-type(2) {{
                width: 100% !important;
                min-height: auto !important;
                height: auto !important;
                padding: 40px 24px !important;
            }}
            [data-testid="column"]:nth-of-type(1) {{
                min-height: 30vh !important;
                align-items: flex-start !important;
            }}
            .brand-title {{ font-size: 28px; }}
            .brand-description {{ font-size: 15px; }}
        }}

        
        /* Remove o quadrado branco injetado pelos wrappers do Streamlit nas colunas do login */
        [data-testid="column"] [data-testid="stVerticalBlockBorderWrapper"] {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            box-shadow: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


    # ========================================================
    # ÚNICO BLOCO DE COLUNAS
    # ========================================================

    col1, col2 = st.columns(
        [1, 1],
        gap="small"
    )


    # ========================================================
    # PAINEL ESQUERDO
    # ========================================================

    with col1:

        st.markdown(
            """
            <div class="logo-box">
                <div class="logo-inner"></div>
            </div>

            <h1 class="brand-title">
                Caminhos da imunização
            </h1>

            <p class="brand-description">
                Gestão de dados de vacinação e deslocamento<br>
                intermunicipal para a rede de saúde do Ceará.
            </p>
            """,
            unsafe_allow_html=True
        )


    # ========================================================
    # PAINEL DIREITO
    # ========================================================

    with col2:

        st.markdown(
            """
            <div class="login-title">
                Entrar na sua conta
            </div>

            <div class="login-subtitle">
                Use suas credenciais de gestor municipal ou estadual.
            </div>
            """,
            unsafe_allow_html=True
        )


        # ====================================================
        # FORMULÁRIO
        # ====================================================

        with st.form(
            "login_form",
            clear_on_submit=False
        ):

            email = st.text_input(
                "E-mail",
                placeholder="nome@saude.ce.gov.br"
            )

            senha = st.text_input(
                "Senha",
                type="password",
                placeholder="********"
            )

            submit = st.form_submit_button(
                "Entrar"
            )


            # =================================================
            # LOGIN
            # =================================================

            if submit:

                # ---------------------------------------------
                # Validação básica
                # ---------------------------------------------

                if not email or not senha:

                    st.error(
                        "Informe o e-mail e a senha."
                    )

                else:

                    try:

                        resp = requests.post(
                            f"{API_URL}/auth/login",
                            json={
                                "email": email,
                                "password": senha
                            },
                            timeout=10
                        )


                        # -------------------------------------
                        # LOGIN OK
                        # -------------------------------------

                        if resp.status_code == 200:

                            data = resp.json()

                            st.session_state["token"] = (
                                data.get("access_token")
                            )

                            st.session_state["role"] = (
                                data.get("role")
                            )

                            st.session_state["municipio_id"] = (
                                data.get("municipio_alocado_id")
                            )

                            st.session_state["_cookie_sync"] = "set"

                            st.rerun()


                        # -------------------------------------
                        # CREDENCIAIS INCORRETAS
                        # -------------------------------------

                        elif resp.status_code in (400, 401, 403):

                            st.error(
                                "E-mail ou senha incorretos."
                            )


                        # -------------------------------------
                        # ERRO DA API
                        # -------------------------------------

                        else:

                            st.error(
                                f"Erro ao realizar login. "
                                f"Código: {resp.status_code}"
                            )


                    except requests.exceptions.ConnectionError:

                        st.error(
                            "Não foi possível conectar ao servidor."
                        )


                    except requests.exceptions.Timeout:

                        st.error(
                            "O servidor demorou para responder."
                        )


                    except requests.exceptions.RequestException:

                        st.error(
                            "Erro de comunicação com o servidor."
                        )


        # ====================================================
        # RECUPERAÇÃO DE SENHA
        # ====================================================

        st.markdown(
            """
            <div class="forgot-pass">
                Esqueceu sua senha? Contate o administrador estadual.
            </div>
            """,
            unsafe_allow_html=True
        )


# ============================================================
# SISTEMA PROTEGIDO
# ============================================================

else:

    # --------------------------------------------------------
    # SIDEBAR: marca, navegação, perfil e logout
    # --------------------------------------------------------

    # O Dashboard passa a ser a primeira opção do menu
    PAGINAS = {
        "dashboard": "📊 Dashboard Geral",
        "registros": "💉 Registros de Vacinação",
        "municipios": "🏙️ Gestão de Municípios & Vacinas",
    }

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-mark"><div class="sidebar-brand-mark-inner"></div></div>
                <div class="sidebar-brand-text">Caminhos da<br>Imunização</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sidebar-section-label">Navegação</div>', unsafe_allow_html=True)
        for chave, rotulo in PAGINAS.items():
            ativo = st.session_state["pagina_ativa"] == chave
            if st.button(
                rotulo,
                key=f"nav_{chave}",
                use_container_width=True,
                type="primary" if ativo else "secondary",
            ):
                st.session_state["pagina_ativa"] = chave
                st.rerun()

        st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
        st.divider()
        st.markdown(
            f'<div class="sidebar-profile">Perfil: <strong>{st.session_state["role"]}</strong></div>',
            unsafe_allow_html=True,
        )

        if st.button("Sair / Logout", key="btn_logout", use_container_width=True):
            st.session_state["token"] = None
            st.session_state["role"] = None
            st.session_state["municipio_id"] = None
            st.session_state["_cookie_sync"] = "clear"
            st.rerun()

    # --------------------------------------------------------
    # CONTEÚDO PRINCIPAL
    # --------------------------------------------------------

    if st.session_state["role"] == "GESTOR_MUNICIPAL":
        st.info(
            "O seu acesso está restrito ao município "
            f"IBGE: {st.session_state['municipio_id']}"
        )

    # Roteamento central das páginas
    if st.session_state["pagina_ativa"] == "dashboard":
        render_dashboard_section()
    elif st.session_state["pagina_ativa"] == "municipios":
        render_municipios_section()
    else:
        render_registros_section()