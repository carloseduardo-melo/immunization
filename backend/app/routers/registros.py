from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import LogAuditoria, Municipio, RegistroVacinacao, Vacina
from app.schemas import (
    PaginatedRegistros,
    RegistroVacinacaoCreate,
    RegistroVacinacaoOut,
    RegistroVacinacaoUpdate,
)

router = APIRouter(prefix="/registros", tags=["Registros"])


def _registro_para_auditoria(registro: RegistroVacinacao) -> dict:
    """Serializa o registro em valores compatíveis com JSON/JSONB para auditoria."""
    return {
        "id": str(registro.id),
        "data_vacinacao": registro.data_vacinacao.isoformat(),
        "idade": registro.idade,
        "vacina_id": registro.vacina_id,
        "municipio_residencia_id": registro.municipio_residencia_id,
        "municipio_vacina_id": registro.municipio_vacina_id,
        "teve_deslocamento": registro.teve_deslocamento,
        "quantidade": registro.quantidade,
        "status_dado": registro.status_dado,
        "ativo": registro.ativo,
    }


def _buscar_registro_ativo(db: Session, id: UUID) -> RegistroVacinacao:
    registro = (
        db.query(RegistroVacinacao)
        .filter(RegistroVacinacao.id == id, RegistroVacinacao.ativo.is_(True))
        .first()
    )
    if not registro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro de vacinação não encontrado.",
        )
    return registro


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
    ).filter(
        RegistroVacinacao.ativo.is_(True)
    )

    if search:
        query = query.filter(
            Municipio.nome.ilike(f"%{search}%") | Vacina.nome.ilike(f"%{search}%")
        )

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    resultados = (
        query.order_by(RegistroVacinacao.data_vacinacao.desc(), RegistroVacinacao.id)
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


@router.put("/{id}", response_model=RegistroVacinacaoOut)
def atualizar_registro(
    id: UUID,
    payload: RegistroVacinacaoUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF08 - Edita (retifica) um registro de vacinação existente e registra a alteração na auditoria."""
    registro = _buscar_registro_ativo(db, id)

    valores_antigos = _registro_para_auditoria(registro)

    status_calculado = "VALIDO"
    if payload.idade is not None and (payload.idade < 0 or payload.idade > 110):
        status_calculado = "DADO_INCONSISTENTE"

    registro.data_vacinacao = payload.data_vacinacao
    registro.municipio_vacina_id = payload.municipio_vacina_id
    registro.municipio_residencia_id = payload.municipio_residencia_id
    registro.vacina_id = payload.vacina_id
    registro.idade = payload.idade
    registro.quantidade = payload.quantidade
    registro.status_dado = status_calculado

    valores_novos = _registro_para_auditoria(registro)

    log = LogAuditoria(
        tabela="registros_vacinacao",
        registro_id=registro.id,
        acao="UPDATE",
        usuario_id=current_user.id,
        valores_antigos=valores_antigos,
        valores_novos=valores_novos,
    )
    db.add(log)
    db.commit()
    db.refresh(registro)

    return registro


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_registro(
    id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Exclui logicamente um registro de vacinação e registra a ação na auditoria."""
    registro = _buscar_registro_ativo(db, id)

    valores_antigos = _registro_para_auditoria(registro)

    # Exclusão lógica: o registro permanece fisicamente no banco.
    registro.ativo = False

    valores_novos = dict(valores_antigos)
    valores_novos["ativo"] = False

    log = LogAuditoria(
        tabela="registros_vacinacao",
        registro_id=registro.id,
        acao="DELETE",
        usuario_id=current_user.id,
        valores_antigos=valores_antigos,
        valores_novos=valores_novos,
    )

    db.add(log)
    db.commit()

    return None
