"""RF15 (varredura de completude) e RF16 (gestão de status dos alertas)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_only
from app.schemas import ResultadoVarredura
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
