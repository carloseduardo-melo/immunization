"""RF19/RF20 - Botões de exportação compartilhados pelas telas de listagem.

O arquivo é montado pelo backend (`/exportacoes/<recurso>` para o CSV,
`/relatorios/<recurso>` para o PDF), com os mesmos filtros que a tela está
aplicando. Aqui cuidamos só do fluxo de dois passos que
o Streamlit exige: `st.download_button` precisa dos bytes prontos no momento em
que é desenhado, então buscar o arquivo direto nele significaria baixar o
recorte inteiro a cada rerun da página, mesmo sem ninguém clicar. Por isso o
primeiro clique busca o arquivo e o segundo botão, que só então aparece,
entrega o download.
"""

import streamlit as st

from api_client import ApiError, exportar_csv, exportar_pdf

ESPERA = "Preparando o arquivo para download..."

# Cada formato tem os seus rótulos e o seu tipo de arquivo; o resto do fluxo
# (espera, bloqueio, descarte quando os filtros mudam) é igual nos dois.
FORMATOS = {
    "csv": ("Exportar CSV", "Baixar CSV", "text/csv", "csv", "exportar"),
    "pdf": ("Exportar PDF", "Baixar PDF", "application/pdf", "pdf", "relatorio"),
}


def _baixar(formato: str, token: str, recurso: str, filtros: dict) -> tuple[bytes, bool]:
    """Escolhe o cliente do formato na hora da chamada.

    Resolver aqui, e não numa tabela montada na importação, é o que mantém a
    função substituível — por um teste ou por qualquer coisa que troque o
    atributo do módulo depois que ele já foi importado."""
    if formato == "csv":
        return exportar_csv(token, recurso, **filtros)
    return exportar_pdf(token, recurso, **filtros)

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
) -> None:
    """RF19 - Botão que baixa a listagem filtrada em CSV."""
    _botao_exportar("csv", token, recurso, filtros, key, nome_arquivo)


def botao_exportar_pdf(
    token: str,
    recurso: str,
    filtros: dict,
    key: str,
    nome_arquivo: str | None = None,
) -> None:
    """RF20 - Botão que baixa o relatório consolidado do painel em PDF."""
    _botao_exportar("pdf", token, recurso, filtros, key, nome_arquivo)


def _botao_exportar(
    formato: str,
    token: str,
    recurso: str,
    filtros: dict,
    key: str,
    nome_arquivo: str | None = None,
) -> None:
    """Desenha o botão de exportação e, após o clique, o botão de download."""
    rotulo, rotulo_download, mime, extensao, prefixo = FORMATOS[formato]
    # Um slot por formato: preparar o CSV não pode liberar nem bloquear o PDF.
    slot = f"_export_{formato}_{key}"
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
        key=f"{prefixo}_{key}",
        use_container_width=True,
        disabled=preparado is not None,
    ):
        try:
            with st.spinner(ESPERA):
                conteudo, truncado = _baixar(formato, token, recurso, filtros)
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
        rotulo_download,
        data=preparado["conteudo"],
        file_name=nome_arquivo or f"{recurso}.{extensao}",
        mime=mime,
        key=f"baixar_{formato}_{key}",
        use_container_width=True,
    )
