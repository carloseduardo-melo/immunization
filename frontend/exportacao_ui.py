"""RF19 - Botão de exportação em CSV, compartilhado pelas telas de listagem.

O arquivo é montado pelo backend (`/exportacoes/<recurso>`), com os mesmos
filtros que a tela está aplicando. Aqui cuidamos só do fluxo de dois passos que
o Streamlit exige: `st.download_button` precisa dos bytes prontos no momento em
que é desenhado, então buscar o arquivo direto nele significaria baixar o
recorte inteiro a cada rerun da página, mesmo sem ninguém clicar. Por isso o
primeiro clique busca o arquivo e o segundo botão, que só então aparece,
entrega o download.
"""

import streamlit as st

from api_client import ApiError, exportar_csv

ESPERA = "Preparando o arquivo para download..."

AVISO_TRUNCADO = (
    "O recorte excedeu o limite de linhas da exportação e o arquivo saiu "
    "incompleto — refine os filtros para levar todos os dados."
)


def _assinatura(filtros: dict) -> tuple:
    """Identidade do recorte, para detectar que os filtros da tela mudaram."""
    return tuple(sorted((chave, str(valor)) for chave, valor in filtros.items()))


def botao_exportar_csv(
    token: str,
    recurso: str,
    filtros: dict,
    key: str,
    nome_arquivo: str | None = None,
    rotulo: str = "Exportar CSV",
) -> None:
    """Desenha o botão "Exportar CSV" e, após o clique, o botão de download."""
    slot = f"_export_{key}"
    assinatura = _assinatura(filtros)

    preparado = st.session_state.get(slot)
    # Arquivo preparado com outro recorte não vale mais: oferecê-lo entregaria
    # ao gestor dados diferentes dos que ele está vendo.
    if preparado and preparado["filtros"] != assinatura:
        preparado = None
        del st.session_state[slot]

    # Bloqueado enquanto o arquivo do recorte atual está pronto para baixar:
    # clicar de novo só repetiria a mesma consulta, que varre o recorte inteiro.
    # Trocar um filtro descarta o arquivo acima e reabilita o botão.
    if st.button(
        rotulo,
        key=f"exportar_{key}",
        use_container_width=True,
        disabled=preparado is not None,
    ):
        try:
            with st.spinner(ESPERA):
                conteudo, truncado = exportar_csv(token, recurso, **filtros)
        except ApiError as exc:
            st.session_state.pop(slot, None)
            st.error(f"Não foi possível exportar: {exc.message}")
            return
        st.session_state[slot] = {
            "filtros": assinatura,
            "conteudo": conteudo,
            "truncado": truncado,
        }
        # O botão desta passagem já foi desenhado habilitado (o arquivo ainda não
        # existia quando ele renderizou). Sem o rerun ele continuaria clicável
        # até a próxima interação do usuário, repetindo a consulta à toa.
        st.rerun()

    if not preparado:
        return

    if preparado["truncado"]:
        st.warning(AVISO_TRUNCADO)

    st.download_button(
        "Baixar CSV",
        data=preparado["conteudo"],
        file_name=nome_arquivo or f"{recurso}.csv",
        mime="text/csv",
        key=f"baixar_{key}",
        use_container_width=True,
    )
