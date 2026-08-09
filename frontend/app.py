import os
import streamlit as st
import requests


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
    initial_sidebar_state="collapsed"
)


# ============================================================
# ESTADO DA SESSÃO
# ============================================================

if "token" not in st.session_state:
    st.session_state["token"] = None

if "role" not in st.session_state:
    st.session_state["role"] = None

if "municipio_id" not in st.session_state:
    st.session_state["municipio_id"] = None


# ============================================================
# TELA DE LOGIN
# ============================================================

if not st.session_state["token"]:

    # --------------------------------------------------------
    # CSS DA TELA DE LOGIN
    # --------------------------------------------------------

    st.markdown(
        """
        <style>

        /* ==================================================
           RESET GERAL DO STREAMLIT
           ================================================== */

        html,
        body,
        [data-testid="stAppViewContainer"],
        [data-testid="stApp"],
        .stApp {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            min-height: 100vh !important;
        }

        /* Remove header */
        [data-testid="stHeader"] {
            display: none !important;
        }

        /* Remove footer */
        footer {
            display: none !important;
        }

        /* Remove menu */
        #MainMenu {
            display: none !important;
        }

        /* Container principal */
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            padding: 0 !important;
            margin: 0 !important;
            max-width: none !important;
            width: 100% !important;
        }

        /* Área principal */
        [data-testid="stAppViewContainer"] > section {
            padding: 0 !important;
            margin: 0 !important;
        }


        /* ==================================================
           BLOCO DE COLUNAS
           ================================================== */

        [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;

            width: 100% !important;
            min-width: 100% !important;

            margin: 0 !important;
            padding: 0 !important;

            gap: 0 !important;

            align-items: stretch !important;
        }


        /* ==================================================
           COLUNA ESQUERDA
           ================================================== */

        [data-testid="stHorizontalBlock"]
        [data-testid="column"]:nth-child(1) {

            background: #5551ff !important;

            min-height: 100vh !important;
            height: 100vh !important;

            padding: 0 10% !important;
            margin: 0 !important;

            display: flex !important;
            align-items: center !important;
            justify-content: center !important;

            box-sizing: border-box !important;
        }


        /* Conteúdo interno da coluna esquerda */

        [data-testid="stHorizontalBlock"]
        [data-testid="column"]:nth-child(1) > div {

            width: 100% !important;
            max-width: 600px !important;

            margin: 0 auto !important;
            padding: 0 !important;
        }


        /* ==================================================
           COLUNA DIREITA
           ================================================== */

        [data-testid="stHorizontalBlock"]
        [data-testid="column"]:nth-child(2) {

            background: #ffffff !important;

            min-height: 100vh !important;
            height: 100vh !important;

            padding: 0 8% !important;
            margin: 0 !important;

            display: flex !important;
            align-items: center !important;
            justify-content: center !important;

            box-sizing: border-box !important;
        }


        /* Conteúdo interno da coluna direita */

        [data-testid="stHorizontalBlock"]
        [data-testid="column"]:nth-child(2) > div {

            width: 100% !important;
            max-width: 360px !important;

            margin: 0 auto !important;
            padding: 0 !important;
        }


        /* ==================================================
           LOGO
           ================================================== */

        .logo-box {

            width: 56px;
            height: 56px;

            background: #ffffff;

            border-radius: 12px;

            display: flex;
            align-items: center;
            justify-content: center;

            margin-bottom: 28px;
        }


        .logo-inner {

            width: 20px;
            height: 20px;

            background: #5551ff;

            border-radius: 4px;
        }


        /* ==================================================
           TEXTO DO PAINEL AZUL
           ================================================== */

        .brand-title {

            margin: 0 0 14px 0;

            color: #ffffff;

            font-size: 34px;
            line-height: 1.2;

            font-weight: 700;

            letter-spacing: -0.6px;
        }


        .brand-description {

            margin: 0;

            color: #e8e8ff;

            font-size: 16px;

            line-height: 1.6;

            font-weight: 400;
        }


        /* ==================================================
           TÍTULO DO LOGIN
           ================================================== */

        .login-title {

            margin: 0 0 8px 0;

            color: #111827;

            font-size: 25px;

            line-height: 1.3;

            font-weight: 700;

            letter-spacing: -0.3px;
        }


        .login-subtitle {

            margin: 0 0 30px 0;

            color: #6b7280;

            font-size: 14px;

            line-height: 1.5;

            font-weight: 400;
        }


        /* ==================================================
           FORMULÁRIO
           ================================================== */

        [data-testid="stForm"] {

            border: none !important;

            padding: 0 !important;

            margin: 0 !important;

            background: transparent !important;
        }


        /* ==================================================
           LABELS
           ================================================== */

        [data-testid="stForm"] label {

            color: #374151 !important;

            font-size: 13px !important;

            font-weight: 500 !important;
        }


        /* ==================================================
           INPUTS
           ================================================== */

        [data-testid="stForm"] input {

            height: 42px !important;

            min-height: 42px !important;

            background: #ffffff !important;

            border: 1px solid #d1d5db !important;

            border-radius: 6px !important;

            color: #111827 !important;

            font-size: 14px !important;

            padding: 0 12px !important;

            box-sizing: border-box !important;
        }


        /* Input quando recebe foco */

        [data-testid="stForm"] input:focus {

            border-color: #5551ff !important;

            box-shadow: 0 0 0 1px #5551ff !important;
        }


        /* ==================================================
           BOTÃO ENTRAR
           ================================================== */

        [data-testid="stFormSubmitButton"] {

            width: 100% !important;

            margin-top: 12px !important;
        }


        [data-testid="stFormSubmitButton"] > button {

            width: 100% !important;

            height: 42px !important;

            min-height: 42px !important;

            background: #5551ff !important;

            color: #ffffff !important;

            border: none !important;

            border-radius: 6px !important;

            font-size: 14px !important;

            font-weight: 600 !important;

            padding: 0 !important;

            margin: 0 !important;

            transition:
                background-color 0.2s ease,
                transform 0.1s ease !important;
        }


        [data-testid="stFormSubmitButton"] > button:hover {

            background: #4541e6 !important;

            color: #ffffff !important;
        }


        [data-testid="stFormSubmitButton"] > button:active {

            transform: translateY(1px);
        }


        /* ==================================================
           MENSAGEM ESQUECEU A SENHA
           ================================================== */

        .forgot-pass {

            margin-top: 18px;

            color: #9ca3af;

            font-size: 12px;

            line-height: 1.5;

            text-align: left;
        }


        /* ==================================================
           RESPONSIVIDADE
           ================================================== */

        @media (max-width: 768px) {

            [data-testid="stHorizontalBlock"] {

                flex-direction: column !important;
            }


            [data-testid="stHorizontalBlock"]
            [data-testid="column"]:nth-child(1) {

                min-height: 360px !important;

                height: auto !important;

                padding: 60px 30px !important;

                align-items: flex-start !important;
            }


            [data-testid="stHorizontalBlock"]
            [data-testid="column"]:nth-child(2) {

                min-height: auto !important;

                height: auto !important;

                padding: 60px 30px !important;
            }


            .brand-title {

                font-size: 28px;
            }


            .brand-description {

                font-size: 15px;
            }


            [data-testid="stHorizontalBlock"]
            [data-testid="column"]:nth-child(2) > div {

                max-width: 420px !important;
            }
        }

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
    # SIDEBAR
    # --------------------------------------------------------

    st.sidebar.title(
        "Navegação"
    )

    st.sidebar.write(
        f"Perfil: **{st.session_state['role']}**"
    )


    # --------------------------------------------------------
    # LOGOUT
    # --------------------------------------------------------

    if st.sidebar.button(
        "Sair / Logout"
    ):

        st.session_state["token"] = None
        st.session_state["role"] = None
        st.session_state["municipio_id"] = None

        st.rerun()


    # --------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------

    st.title(
        "Painel de Controle"
    )

    st.success(
        "Login efetuado com sucesso. "
        "Bem-vindo ao Caminhos da Imunização!"
    )


    # --------------------------------------------------------
    # RESTRIÇÃO MUNICIPAL
    # --------------------------------------------------------

    if st.session_state["role"] == "GESTOR_MUNICIPAL":

        st.info(
            "O seu acesso está restrito ao município "
            f"IBGE: {st.session_state['municipio_id']}"
        )