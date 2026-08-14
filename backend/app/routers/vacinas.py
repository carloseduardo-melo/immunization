from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_and_estadual, get_current_user
from app.models import Vacina
from app.schemas import PaginatedVacinas, VacinaCreate, VacinaOut, VacinaUpdate

router = APIRouter(prefix="/vacinas", tags=["Vacinas"])


@router.get("", response_model=PaginatedVacinas)
def listar_vacinas(
    alta_complexidade: Optional[bool] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF04 - Listar, filtrar e paginar vacinas"""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100

    query = db.query(Vacina)
    
    if alta_complexidade is not None:
        query = query.filter(Vacina.alta_complexidade == alta_complexidade)
    
    if ativo is not None:
        query = query.filter(Vacina.ativo == ativo)
    
    if search:
        query = query.filter(Vacina.nome.ilike(f"%{search}%"))

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    items = (
        query.order_by(Vacina.nome)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedVacinas(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=VacinaOut, status_code=status.HTTP_201_CREATED)
def criar_vacina(
    payload: VacinaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """RF05 - Cadastrar vacina (com padronização e trava de perfil)"""
    nome_padronizado = payload.nome.strip()

    # Validação de Nomenclatura Duplicada (Case Insensitive)
    existente = db.query(Vacina).filter(func.lower(Vacina.nome) == nome_padronizado.lower()).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma vacina cadastrada com este nome.",
        )

    # Regra de Negócio: Apenas ADMIN pode setar alta_complexidade = True
    if payload.alta_complexidade and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas usuários com perfil Administrador podem marcar uma vacina como alta complexidade.",
        )

    vacina = Vacina(
        nome=nome_padronizado,
        alta_complexidade=payload.alta_complexidade,
        ativo=True,
    )
    db.add(vacina)
    db.commit()
    db.refresh(vacina)
    return vacina


@router.put("/{vacina_id}", response_model=VacinaOut)
def atualizar_vacina(
    vacina_id: int,
    payload: VacinaUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """RF05 - Editar vacina"""
    vacina = db.query(Vacina).filter(Vacina.id == vacina_id).first()
    if not vacina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacina não encontrada.")

    nome_padronizado = payload.nome.strip()

    # Validação de Nomenclatura Duplicada garantindo que não estamos checando contra a própria vacina
    existente = db.query(Vacina).filter(
        func.lower(Vacina.nome) == nome_padronizado.lower(), 
        Vacina.id != vacina_id
    ).first()
    
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe outra vacina cadastrada com este nome.",
        )

    # Regra de Negócio: Se houver mudança na alta_complexidade, checar perfil
    if payload.alta_complexidade != vacina.alta_complexidade:
        if current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores podem alterar a complexidade de uma vacina.",
            )

    vacina.nome = nome_padronizado
    vacina.alta_complexidade = payload.alta_complexidade
    db.commit()
    db.refresh(vacina)
    return vacina


@router.delete("/{vacina_id}", response_model=VacinaOut)
def desativar_vacina(
    vacina_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_and_estadual),
):
    """RF05 - Apenas desativa a vacina (ativo = false)"""
    vacina = db.query(Vacina).filter(Vacina.id == vacina_id).first()
    if not vacina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacina não encontrada.")

    vacina.ativo = False
    db.commit()
    db.refresh(vacina)
    return vacina