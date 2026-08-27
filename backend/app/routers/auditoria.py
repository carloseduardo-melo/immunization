"""RF22 - consulta do log de auditoria, restrita ao perfil Administrador.

Este router é deliberadamente somente-leitura: não existe POST, PUT, PATCH nem
DELETE sobre `log_auditoria` em lugar nenhum da API. É assim que o RNF09 é
cumprido — a imutabilidade vem da ausência de rota, não de uma checagem que
alguém possa esquecer de aplicar.
"""

from datetime import date
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_only
from app.schemas import LogAuditoriaOut, PaginatedLogs, UsuarioAuditoriaOut
from app.services.auditoria import construir_query_logs, listar_usuarios_com_log

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

PAGE_SIZE_PADRAO = 10
PAGE_SIZE_MAXIMO = 100


@router.get(
    "",
    response_model=PaginatedLogs,
    summary="Consultar log de auditoria",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Consulta restrita ao perfil Administrador."},
    },
)
def listar_auditoria(
    usuario_id: Optional[UUID] = None,
    tabela: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_only),
):
    """RF22 - Lista as alterações registradas, da mais recente para a mais antiga.

    Filtros combináveis por autor, tabela alterada e período (`data_fim` é
    inclusiva). Cada linha traz os valores antigos e novos completos, para que a
    tela possa mostrar a diferença campo a campo."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = PAGE_SIZE_PADRAO
    if page_size > PAGE_SIZE_MAXIMO:
        page_size = PAGE_SIZE_MAXIMO

    query = construir_query_logs(
        db,
        usuario_id=usuario_id,
        tabela=tabela,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    resultados = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        LogAuditoriaOut(
            id=log.id,
            tabela=log.tabela,
            registro_id=log.registro_id,
            acao=log.acao,
            usuario_id=log.usuario_id,
            usuario_email=usuario_email,
            valores_antigos=log.valores_antigos,
            valores_novos=log.valores_novos,
            criado_em=log.criado_em,
        )
        for log, usuario_email in resultados
    ]

    return PaginatedLogs(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/usuarios",
    response_model=list[UsuarioAuditoriaOut],
    summary="Listar autores presentes no log",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Consulta restrita ao perfil Administrador."},
    },
)
def listar_autores(
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_only),
):
    """RF22 - Usuários que têm ao menos um registro no log, para o filtro por autor."""
    return [
        UsuarioAuditoriaOut(id=usuario.id, email=usuario.email)
        for usuario in listar_usuarios_com_log(db)
    ]
