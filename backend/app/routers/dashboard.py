from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import RegistroVacinacao
from app.dependencies import get_current_user
from app.schemas import DashboardResumo

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get(
    "/resumo",
    response_model=DashboardResumo,
    summary="Obter resumo do dashboard",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_resumo_dashboard(
    municipio_id: Optional[str] = None,
    vacina_id: Optional[int] = None,
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF23 - Retorna os KPIs (total de doses, deslocamentos, taxa de mobilidade e
    inconsistências) e a série temporal mensal para o gráfico do Dashboard,
    considerando apenas registros ativos. Aceita filtros opcionais por
    município, vacina e ano."""
    
    # Inicia a query garantindo que apenas registros ATIVOS sejam contabilizados
    query = db.query(RegistroVacinacao).filter(RegistroVacinacao.ativo == True)
    
    if municipio_id:
        query = query.filter(RegistroVacinacao.municipio_vacina_id == municipio_id)
    if vacina_id:
        query = query.filter(RegistroVacinacao.vacina_id == vacina_id)
    if ano:
        query = query.filter(func.extract('year', RegistroVacinacao.data_vacinacao) == ano)

    total_doses = query.with_entities(func.coalesce(func.sum(RegistroVacinacao.quantidade), 0)).scalar()
    
    total_deslocamentos = query.filter(
        RegistroVacinacao.teve_deslocamento == True,
        RegistroVacinacao.status_dado != "DADO_INCONSISTENTE"
    ).with_entities(func.coalesce(func.sum(RegistroVacinacao.quantidade), 0)).scalar()
    
    total_inconsistentes = query.filter(
        RegistroVacinacao.status_dado == "DADO_INCONSISTENTE"
    ).with_entities(func.coalesce(func.sum(RegistroVacinacao.quantidade), 0)).scalar()
    
    taxa_mobilidade = round((total_deslocamentos / total_doses * 100), 2) if total_doses > 0 else 0.0

    # Agrupa por ano/mês com `extract`, que o SQLAlchemy traduz tanto para
    # PostgreSQL (produção) quanto para SQLite (dev.db/test.db). O `date_trunc`
    # usado antes só existe no PostgreSQL e quebrava o dashboard localmente.
    ano_col = func.extract('year', RegistroVacinacao.data_vacinacao).label('ano')
    mes_col = func.extract('month', RegistroVacinacao.data_vacinacao).label('mes_num')

    serie_temporal = query.filter(RegistroVacinacao.status_dado != "DADO_INCONSISTENTE") \
        .with_entities(
            ano_col,
            mes_col,
            RegistroVacinacao.teve_deslocamento,
            func.sum(RegistroVacinacao.quantidade).label('total')
        ) \
        .group_by(ano_col, mes_col, RegistroVacinacao.teve_deslocamento) \
        .order_by(ano_col, mes_col) \
        .all()

    grafico_dados = [
        {
            "mes": f"{int(row.ano):04d}-{int(row.mes_num):02d}"
            if row.ano is not None and row.mes_num is not None
            else "Desconhecido",
            "deslocou": row.teve_deslocamento,
            "total": row.total
        }
        for row in serie_temporal
    ]

    return {
        "kpis": {
            "total_doses": total_doses,
            "total_deslocamentos": total_deslocamentos,
            "taxa_mobilidade": taxa_mobilidade,
            "total_inconsistentes": total_inconsistentes
        },
        "grafico": grafico_dados
    }