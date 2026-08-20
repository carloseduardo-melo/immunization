"""RF15 (varredura de completude) e RF16 (gestão de status dos alertas)."""

from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_only, get_current_user, validate_municipio_scope
from app.models import AlertaCompletude
from app.schemas import AlertaCompletudeOut, PaginatedAlertas, ResultadoVarredura
from app.services.completude import K_PADRAO, detectar_anomalias

router = APIRouter(prefix="/completude", tags=["Completude"])

STATUS_VALIDOS = ("ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO")
PAGE_SIZE_PADRAO = 10
PAGE_SIZE_MAXIMO = 100


@router.post(
    "/recalcular",
    response_model=ResultadoVarredura,
    summary="Executa a varredura de completude e grava os alertas",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Operação restrita ao perfil Administrador."},
    },
)
def recalcular_completude(
    k: float = K_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_only),
):
    """RF15 - Recalcula o volume mensal por município, compara com a faixa
    esperada (média - k·desvio) e registra em `alertas_completude` os meses fora
    do padrão. Alertas já existentes têm o total atualizado e o status
    preservado."""
    return detectar_anomalias(db, k=k)


def _alerta_out(alerta: AlertaCompletude) -> AlertaCompletudeOut:
    """Serializa o alerta já com o nome do município resolvido pelo relationship."""
    return AlertaCompletudeOut(
        id=alerta.id,
        referencia_ano=alerta.referencia_ano,
        referencia_mes=alerta.referencia_mes,
        municipio_id=alerta.municipio_id,
        municipio_nome=alerta.municipio.nome if alerta.municipio else None,
        total_observado=alerta.total_observado,
        status=alerta.status,
        criado_em=alerta.criado_em,
    )


@router.get(
    "/alertas",
    response_model=PaginatedAlertas,
    summary="Lista os alertas de completude, com filtro por status",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def listar_alertas(
    status: Optional[str] = None,
    municipio_id: Optional[str] = None,
    ano: Optional[int] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF16 - Lista os alertas gerados pela varredura, do mês mais recente para o
    mais antigo, com filtros opcionais por status, município e ano.

    Gestores municipais enxergam apenas o município ao qual estão vinculados. Os
    contadores de KPI (`totais_por_status`, `municipios_afetados`) desconsideram o
    filtro de status, para a tela mostrar a distribuição completa do recorte."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = PAGE_SIZE_PADRAO
    if page_size > PAGE_SIZE_MAXIMO:
        page_size = PAGE_SIZE_MAXIMO

    if current_user.role == "GESTOR_MUNICIPAL":
        validate_municipio_scope(current_user, municipio_id)
        municipio_id = current_user.municipio_alocado_id

    # Filtros de recorte (sem o status): valem para a listagem e para os KPIs.
    base = db.query(AlertaCompletude)
    if municipio_id:
        base = base.filter(AlertaCompletude.municipio_id == municipio_id)
    if ano:
        base = base.filter(AlertaCompletude.referencia_ano == ano)

    contagens = dict(
        base.with_entities(AlertaCompletude.status, func.count(AlertaCompletude.id))
        .group_by(AlertaCompletude.status)
        .all()
    )
    totais_por_status = {chave: int(contagens.get(chave, 0)) for chave in STATUS_VALIDOS}
    municipios_afetados = base.with_entities(
        func.count(func.distinct(AlertaCompletude.municipio_id))
    ).scalar()

    query = base
    if status:
        query = query.filter(AlertaCompletude.status == status)

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0
    linhas = (
        query.order_by(
            AlertaCompletude.referencia_ano.desc(),
            AlertaCompletude.referencia_mes.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedAlertas(
        items=[_alerta_out(alerta) for alerta in linhas],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        totais_por_status=totais_por_status,
        municipios_afetados=int(municipios_afetados or 0),
    )
