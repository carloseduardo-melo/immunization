from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Municipio, RegistroVacinacao, Vacina
from app.schemas import PaginatedRegistros, RegistroVacinacaoCreate, RegistroVacinacaoOut

router = APIRouter(prefix="/registros", tags=["Registros"])

@router.get("", response_model=PaginatedRegistros)
def listar_registros(
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista e pagina os registros de vacinação, incluindo nomes dos municípios e vacinas."""
    if page < 1: page = 1
    if page_size < 1: page_size = 10

    query = db.query(
        RegistroVacinacao, 
        Municipio.nome.label("municipio_vacina_nome"), 
        Vacina.nome.label("vacina_nome")
    ).outerjoin(
        Municipio, RegistroVacinacao.municipio_vacina_id == Municipio.id_ibge
    ).outerjoin(
        Vacina, RegistroVacinacao.vacina_id == Vacina.id
    )

    if search:
        query = query.filter(
            Municipio.nome.ilike(f"%{search}%") | Vacina.nome.ilike(f"%{search}%")
        )

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    resultados = (
        query.order_by(RegistroVacinacao.data_vacinacao.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for reg, mun_nome, vac_nome in resultados:
        # Converte o objeto SQLAlchemy para dicionário
        reg_dict = {c.name: getattr(reg, c.name) for c in reg.__table__.columns}
        
        # Injeta os nomes resolvidos pelos JOINs
        reg_dict["municipio_vacina_nome"] = mun_nome
        reg_dict["vacina_nome"] = vac_nome
        
        # Como o schema exige municipio_residencia_nome (opcional), garantimos a chave
        reg_dict["municipio_residencia_nome"] = None 
        
        items.append(reg_dict)

    return PaginatedRegistros(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=RegistroVacinacaoOut, status_code=status.HTTP_201_CREATED)
def criar_registro(
    payload: RegistroVacinacaoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cria um novo registro manual de vacinação."""
    
    # 1. Validação de Idade (Regra do Banco)
    status_calculado = "VALIDO"
    if payload.idade is not None:
        if payload.idade < 0 or payload.idade > 110:
            status_calculado = "DADO_INCONSISTENTE"

    # 2. Criação do Registro
    novo_registro = RegistroVacinacao(
        data_vacinacao=payload.data_vacinacao,
        municipio_vacina_id=payload.municipio_vacina_id,
        municipio_residencia_id=payload.municipio_residencia_id,
        vacina_id=payload.vacina_id,
        idade=payload.idade,
        quantidade=payload.quantidade,
        status_dado=status_calculado,
        teve_deslocamento=None # A ser preenchido futuramente
    )
    
    db.add(novo_registro)
    db.commit()
    db.refresh(novo_registro)
    
    # Retorna o modelo recém-criado
    return novo_registro