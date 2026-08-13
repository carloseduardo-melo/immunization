from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_and_estadual, get_current_user
from app.models import Municipio
from app.schemas import MunicipioCreate, MunicipioOut, MunicipioUpdate, PaginatedMunicipios

router = APIRouter(prefix="/municipios", tags=["Municípios"])


@router.get("", response_model=PaginatedMunicipios)
def listar_municipios(
    uf: Optional[str] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    query = db.query(Municipio)
    if uf:
        query = query.filter(Municipio.uf == uf.upper())
    if ativo is not None:
        query = query.filter(Municipio.ativo == ativo)
    if search:
        query = query.filter(Municipio.nome.ilike(f"%{search}%"))

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    items = (
        query.order_by(Municipio.nome)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedMunicipios(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
