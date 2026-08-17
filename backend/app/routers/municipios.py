from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_and_estadual, get_current_user
from app.models import Municipio
from app.schemas import MunicipioCreate, MunicipioOut, MunicipioUpdate, PaginatedMunicipios

router = APIRouter(prefix="/municipios", tags=["Municípios"])


@router.get(
    "",
    response_model=PaginatedMunicipios,
    summary="Listar municípios",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def listar_municipios(
    uf: Optional[str] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista e pagina municípios, com filtros opcionais por UF, status ativo e busca por nome."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100

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


@router.post(
    "",
    response_model=MunicipioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar município",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Perfil sem permissão (requer ADMIN ou GESTOR_ESTADUAL)."},
        409: {"description": "Já existe um município cadastrado com este código IBGE."},
    },
)
def criar_municipio(
    payload: MunicipioCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """Cadastra um novo município. Requer perfil ADMIN ou GESTOR_ESTADUAL."""
    existente = db.query(Municipio).filter(Municipio.id_ibge == payload.id_ibge).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um município cadastrado com este código IBGE.",
        )

    municipio = Municipio(
        id_ibge=payload.id_ibge,
        nome=payload.nome,
        uf=payload.uf,
        regiao_saude=payload.regiao_saude,
        polo=payload.polo,
    )
    db.add(municipio)
    db.commit()
    db.refresh(municipio)
    return municipio


@router.put(
    "/{id_ibge}",
    response_model=MunicipioOut,
    summary="Editar município",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Perfil sem permissão (requer ADMIN ou GESTOR_ESTADUAL)."},
        404: {"description": "Município não encontrado."},
    },
)
def atualizar_municipio(
    id_ibge: str,
    payload: MunicipioUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """Atualiza nome, UF, região de saúde e polo de um município existente. Requer perfil ADMIN ou GESTOR_ESTADUAL."""
    municipio = db.query(Municipio).filter(Municipio.id_ibge == id_ibge).first()
    if not municipio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Município não encontrado.")

    municipio.nome = payload.nome
    municipio.uf = payload.uf
    municipio.regiao_saude = payload.regiao_saude
    municipio.polo = payload.polo
    db.commit()
    db.refresh(municipio)
    return municipio


@router.delete(
    "/{id_ibge}",
    response_model=MunicipioOut,
    summary="Desativar município",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Perfil sem permissão (requer ADMIN ou GESTOR_ESTADUAL)."},
        404: {"description": "Município não encontrado."},
    },
)
def desativar_municipio(
    id_ibge: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """Desativa (ativo=false) um município. Não é uma exclusão física. Requer perfil ADMIN ou GESTOR_ESTADUAL."""
    municipio = db.query(Municipio).filter(Municipio.id_ibge == id_ibge).first()
    if not municipio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Município não encontrado.")

    municipio.ativo = False
    db.commit()
    db.refresh(municipio)
    return municipio
