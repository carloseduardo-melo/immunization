"""RF20 - Montagem do relatório consolidado em PDF de cada painel.

Todo endpoint de `/relatorios` termina aqui: recebe o título, os filtros que a
tela aplicou, a tabela e (quando o painel tem um) os dados do gráfico, e devolve
a resposta HTTP pronta. O documento é feito para prestação de contas, então o
cabeçalho registra quem emitiu e quando, e o bloco de filtros declara o recorte
exato - um relatório oficial não pode deixar dúvida sobre a que dados se refere.

O gráfico é redesenhado em vetor pelo próprio reportlab a partir dos mesmos
números da tabela; ele fica parecido, não idêntico, ao da tela (que é do
Streamlit e não existe no servidor).
"""

from datetime import datetime
from io import BytesIO
from typing import Any, Optional, Sequence

from fastapi.responses import StreamingResponse
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Teto bem menor que o do CSV (50.000): um PDF de dezenas de milhares de linhas
# não se lê nem se imprime. Passando disto, o documento sai com as primeiras
# linhas e diz isso na cara, logo abaixo da tabela.
LIMITE_LINHAS = 500

MARCA = "Caminhos da Imunização"
VAZIO = "—"

AZUL = colors.HexColor("#1d4ed8")
CINZA_ESCURO = colors.HexColor("#3f3f46")
CINZA_CLARO = colors.HexColor("#f4f4f5")
CINZA_LINHA = colors.HexColor("#d4d4d8")


def cortar_no_limite(linhas: Sequence[Any]) -> tuple[list, bool]:
    """Devolve as linhas até o teto do PDF e se o recorte foi truncado."""
    if len(linhas) > LIMITE_LINHAS:
        return list(linhas[:LIMITE_LINHAS]), True
    return list(linhas), False


def texto(valor: Any) -> str:
    """Célula da tabela. Nulo e vazio viram travessão, como na tela."""
    if valor is None or valor == "":
        return VAZIO
    return str(valor)


def _estilos():
    base = getSampleStyleSheet()
    return {
        "marca": ParagraphStyle(
            "marca", parent=base["Normal"], fontSize=9, textColor=AZUL,
            fontName="Helvetica-Bold", spaceAfter=2,
        ),
        "titulo": ParagraphStyle(
            "titulo", parent=base["Title"], fontSize=16, alignment=0,
            textColor=CINZA_ESCURO, spaceAfter=2,
        ),
        "emissao": ParagraphStyle(
            "emissao", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#71717a"),
        ),
        "secao": ParagraphStyle(
            "secao", parent=base["Heading2"], fontSize=11, textColor=CINZA_ESCURO,
            spaceBefore=10, spaceAfter=4,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"], fontSize=8,
            textColor=colors.HexColor("#71717a"), spaceBefore=4,
        ),
        "celula": ParagraphStyle(
            "celula", parent=base["Normal"], fontSize=7.5, leading=9.5,
        ),
        "celula_cabecalho": ParagraphStyle(
            "celula_cabecalho", parent=base["Normal"], fontSize=7.5, leading=9.5,
            textColor=colors.white, fontName="Helvetica-Bold",
        ),
    }


def _cabecalho(estilos, titulo: str, emitido_por: str, emitido_em: datetime) -> list:
    return [
        Paragraph(MARCA, estilos["marca"]),
        Paragraph(titulo, estilos["titulo"]),
        Paragraph(
            f"Emitido em {emitido_em.strftime('%d/%m/%Y às %H:%M')} por {emitido_por}",
            estilos["emissao"],
        ),
        Spacer(1, 8),
    ]


def _bloco_filtros(estilos, filtros: Sequence[tuple[str, Any]]) -> list:
    """Declara o recorte do documento, um filtro por linha."""
    linhas = [
        [
            Paragraph(f"<b>{rotulo}</b>", estilos["celula"]),
            Paragraph(texto(valor), estilos["celula"]),
        ]
        for rotulo, valor in filtros
    ]
    tabela = Table(linhas, colWidths=[45 * mm, 100 * mm], hAlign="LEFT")
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CINZA_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [Paragraph("Filtros aplicados", estilos["secao"]), tabela]


def _grafico(titulo: str, rotulos: Sequence[str], valores: Sequence[float], largura: float):
    """Barras verticais do painel, redesenhadas a partir dos dados da tabela."""
    desenho = Drawing(largura, 150)
    barras = VerticalBarChart()
    barras.x = 30
    barras.y = 30
    barras.width = largura - 50
    barras.height = 100
    barras.data = [list(valores)]
    barras.categoryAxis.categoryNames = list(rotulos)
    barras.categoryAxis.labels.angle = 20
    barras.categoryAxis.labels.dy = -8
    barras.categoryAxis.labels.boxAnchor = "ne"
    barras.categoryAxis.labels.fontSize = 6
    barras.valueAxis.valueMin = 0
    barras.valueAxis.labels.fontSize = 6
    barras.bars[0].fillColor = AZUL
    desenho.add(barras)
    return desenho


def _tabela(estilos, colunas: Sequence[str], linhas: Sequence[Sequence[Any]], largura: float):
    dados = [[Paragraph(coluna, estilos["celula_cabecalho"]) for coluna in colunas]]
    dados += [
        [Paragraph(texto(celula), estilos["celula"]) for celula in linha]
        for linha in linhas
    ]
    tabela = Table(
        dados,
        colWidths=[largura / len(colunas)] * len(colunas),
        # O cabeçalho se repete a cada página: sem isto, da segunda página em
        # diante ninguém sabe que coluna é qual.
        repeatRows=1,
        hAlign="LEFT",
    )
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
                ("GRID", (0, 0), (-1, -1), 0.3, CINZA_LINHA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tabela


def _rodape(canvas, documento):
    """Numeração de página, escrita em cada página no momento em que ela fecha."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#71717a"))
    canvas.drawRightString(
        documento.pagesize[0] - 15 * mm,
        10 * mm,
        f"{MARCA} — página {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def resposta_pdf(
    nome_arquivo: str,
    titulo: str,
    emitido_por: str,
    filtros: Sequence[tuple[str, Any]],
    colunas: Sequence[str],
    linhas: Sequence[Sequence[Any]],
    total: int,
    truncado: bool = False,
    vazio: str = "Nenhum registro encontrado para os filtros aplicados.",
    grafico: Optional[tuple[str, Sequence[str], Sequence[float]]] = None,
    emitido_em: Optional[datetime] = None,
) -> StreamingResponse:
    """Documento do painel: cabeçalho, filtros, gráfico (se houver) e tabela."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=15 * mm,
        title=titulo,
        author=MARCA,
    )
    largura = documento.width
    estilos = _estilos()

    historia: list = _cabecalho(
        estilos, titulo, emitido_por, emitido_em or datetime.now()
    )
    historia += _bloco_filtros(estilos, filtros)

    if not linhas:
        historia.append(Paragraph(vazio, estilos["nota"]))
    else:
        if grafico:
            titulo_grafico, rotulos, valores = grafico
            historia.append(
                KeepTogether(
                    [
                        Paragraph(titulo_grafico, estilos["secao"]),
                        _grafico(titulo_grafico, rotulos, valores, largura),
                    ]
                )
            )
        historia.append(Paragraph("Dados do painel", estilos["secao"]))
        historia.append(_tabela(estilos, colunas, linhas, largura))
        if truncado:
            historia.append(
                Paragraph(
                    f"Exibindo as primeiras {len(linhas)} de {total} linhas do "
                    "recorte. Refine os filtros para um relatório completo.",
                    estilos["nota"],
                )
            )
        else:
            historia.append(
                Paragraph(f"Total de {total} linha(s) no recorte.", estilos["nota"])
            )

    documento.build(historia, onFirstPage=_rodape, onLaterPages=_rodape)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}"',
            "X-Export-Truncated": "true" if truncado else "false",
        },
    )
