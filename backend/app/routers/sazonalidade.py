"""RF17 - Painel de sazonalidade: volume de vacinação por mês do ano.

As doze barras consolidam todos os anos do recorte (Jan..Dez). A série
cronológica ano-a-mês já existe em `/dashboard/resumo`; aqui a pergunta é outra:
"em qual mês do ano concentrar a campanha".

A agregação usa `func.extract`, que o SQLAlchemy traduz tanto para PostgreSQL
(produção) quanto para SQLite (dev.db/test.db) - o mesmo cuidado já tomado em
dashboard.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegistroVacinacao
from app.schemas import SazonalidadeKPIs, SazonalidadeMes, SazonalidadeResponse

router = APIRouter(prefix="/sazonalidade", tags=["Sazonalidade"])

NOMES_MESES = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


@router.get(
    "",
    response_model=SazonalidadeResponse,
    summary="Volume de vacinação por mês do ano",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_sazonalidade(
    vacina_id: Optional[int] = None,
    municipio_id: Optional[str] = None,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF17 - Retorna o total de doses de cada mês do ano (1 a 12), o índice de
    sazonalidade de cada mês (total do mês dividido pela média mensal) e os KPIs
    de pico, vale e amplitude.

    Considera todos os `status_dado`: o mês vem de `data_vacinacao`, que é
    obrigatória e não é afetada pelas inconsistências de idade ou deslocamento -
    completude de volume não é validade do dado. Registros inativos ficam de
    fora. `municipio_id` filtra pelo município de aplicação, como no Dashboard.
    """
    query = db.query(RegistroVacinacao).filter(RegistroVacinacao.ativo == True)

    if vacina_id:
        query = query.filter(RegistroVacinacao.vacina_id == vacina_id)
    if municipio_id:
        query = query.filter(RegistroVacinacao.municipio_vacina_id == municipio_id)

    ano_col = func.extract("year", RegistroVacinacao.data_vacinacao)
    if ano_inicio:
        query = query.filter(ano_col >= ano_inicio)
    if ano_fim:
        query = query.filter(ano_col <= ano_fim)

    mes_col = func.extract("month", RegistroVacinacao.data_vacinacao).label("mes")
    linhas = (
        query.with_entities(
            mes_col, func.sum(RegistroVacinacao.quantidade).label("total")
        )
        .group_by(mes_col)
        .all()
    )
    totais = {int(linha.mes): int(linha.total) for linha in linhas}

    total_periodo = sum(totais.values())
    # Divisor fixo em 12 (e não "meses com dado"): assim o índice de um mês
    # zerado é 0,0 e a soma dos doze índices é sempre 12, independente de
    # quantos meses têm registro.
    media_mensal = total_periodo / 12

    meses = [
        SazonalidadeMes(
            mes=numero,
            nome_mes=NOMES_MESES[numero - 1],
            total_doses=totais.get(numero, 0),
            indice_sazonalidade=(
                round(totais.get(numero, 0) / media_mensal, 2) if media_mensal else 0.0
            ),
        )
        for numero in range(1, 13)
    ]

    kpis = SazonalidadeKPIs(
        total_periodo=total_periodo,
        media_mensal=round(media_mensal, 2),
        amplitude=0.0,
    )

    if total_periodo:
        # Empate resolvido pelo menor número de mês, nos dois extremos, para a
        # resposta ser determinística.
        pico = max(meses, key=lambda mes: (mes.total_doses, -mes.mes))
        vale = min(meses, key=lambda mes: (mes.total_doses, mes.mes))
        kpis.mes_pico = pico.mes
        kpis.mes_pico_nome = pico.nome_mes
        kpis.mes_vale = vale.mes
        kpis.mes_vale_nome = vale.nome_mes
        if vale.total_doses:
            kpis.amplitude = round(pico.total_doses / vale.total_doses, 2)

    return SazonalidadeResponse(kpis=kpis, meses=meses)
