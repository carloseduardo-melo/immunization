"""RF19 - Montagem dos arquivos CSV exportados pelas telas de listagem.

Todo endpoint de `/exportacoes` termina aqui: recebe o cabeçalho e as linhas já
filtradas e devolve a resposta HTTP pronta. Centralizar isto garante que os sete
arquivos gerados pelo sistema tenham o mesmo dialeto e o mesmo comportamento de
truncamento.

Dialeto: separador `;` e BOM UTF-8. É o que o Excel em português abre com um
duplo clique, sem assistente de importação e sem quebrar a acentuação - o
formato continua sendo um CSV válido, com o cabeçalho na primeira linha.
"""

import csv
import io
from typing import Any, Iterable, Iterator, Sequence

from fastapi.responses import StreamingResponse

# Teto de segurança: `/registros` sozinho tem milhões de linhas, e uma
# exportação sem limite prenderia o worker por minutos. Quando o recorte estoura
# o teto, o arquivo sai com as primeiras linhas e o cabeçalho X-Export-Truncated
# avisa a tela, que alerta o usuário a refinar os filtros.
LIMITE_LINHAS = 50_000

SEPARADOR = ";"
VAZIO = "—"


def limite_consulta() -> int:
    """Quantas linhas pedir ao banco: uma a mais que o teto.

    A linha excedente nunca é escrita no arquivo; ela só existe para distinguir
    "o recorte tem exatamente o teto" de "o recorte é maior que o teto".
    """
    return LIMITE_LINHAS + 1


def cortar_no_limite(linhas: Sequence[Any]) -> tuple[list, bool]:
    """Devolve as linhas até o teto e se o recorte foi truncado."""
    if len(linhas) > LIMITE_LINHAS:
        return list(linhas[:LIMITE_LINHAS]), True
    return list(linhas), False


def texto(valor: Any) -> str:
    """Converte um campo para célula. Nulo e vazio viram travessão, como na tela."""
    if valor is None or valor == "":
        return VAZIO
    return str(valor)


def numero(valor: Any) -> str:
    """Decimal com vírgula: é assim que o Excel em português lê um número.

    Casado com o separador `;`, não há ambiguidade entre o separador de coluna
    e o separador decimal."""
    return str(valor).replace(".", ",")


def sim_nao(valor: Any) -> str:
    """Booleano em português; nulo (informação ausente) vira travessão."""
    if valor is None:
        return VAZIO
    return "Sim" if valor else "Não"


def _gerar(cabecalho: Sequence[str], linhas: Iterable[Sequence[Any]]) -> Iterator[str]:
    """Escreve o arquivo linha a linha, reaproveitando um único buffer."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=SEPARADOR, lineterminator="\r\n")

    def _despejar() -> str:
        conteudo = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return conteudo

    escritor.writerow(cabecalho)
    # BOM antes de tudo: é o que faz o Excel ler o arquivo como UTF-8.
    yield "\ufeff" + _despejar()

    for linha in linhas:
        escritor.writerow(linha)
        yield _despejar()


def resposta_csv(
    nome_arquivo: str,
    cabecalho: Sequence[str],
    linhas: Iterable[Sequence[Any]],
    truncado: bool = False,
) -> StreamingResponse:
    """Resposta HTTP de download do CSV, com cabeçalho na primeira linha."""
    return StreamingResponse(
        _gerar(cabecalho, linhas),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            "X-Export-Truncated": "true" if truncado else "false",
        },
    )
