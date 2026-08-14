from datetime import date
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.schemas import PaginatedRegistros, RegistroVacinacaoCreate, RegistroVacinacaoOut

router = APIRouter(prefix="/registros", tags=["Registros de Vacinação"])


@router.get("", response_model=PaginatedRegistros)
def listar_registros(
    municipio_id: Optional[str] = Query(None, description="Código IBGE do município (vacina ou residência)"),
    vacina_id: Optional[int] = Query(None, description="ID da vacina"),
    data_inicio: Optional[date] = Query(None, description="Data inicial para o período"),
    data_fim: Optional[date] = Query(None, description="Data final para o período"),
    idade_min: Optional[int] = Query(None, description="Idade mínima"),
    idade_max: Optional[int] = Query(None, description="Idade máxima"),
    status_dado: Optional[str] = Query(None, description="Status do dado (VALIDO, DADO_INCONSISTENTE, DESLOCAMENTO_INDETERMINADO)"),
    page: int = Query(1, ge=1, description="Número da página"),
    page_size: int = Query(10, ge=1, le=100, description="Tamanho da página"),
    db: Session = Depends(get_db),
    current_user: UsuarioAdmin = Depends(get_current_user),
):
    """RF06 - Consulta dos registros de vacinação com filtros por município, vacina, período e faixa etária."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100

    mun_vacina = aliased(Municipio, name="mun_vacina")
    mun_residencia = aliased(Municipio, name="mun_residencia")

    query = (
        db.query(
            RegistroVacinacao,
            Vacina.nome.label("vacina_nome"),
            mun_vacina.nome.label("municipio_vacina_nome"),
            mun_residencia.nome.label("municipio_residencia_nome"),
        )
        .outerjoin(Vacina, RegistroVacinacao.vacina_id == Vacina.id)
        .outerjoin(mun_vacina, RegistroVacinacao.municipio_vacina_id == mun_vacina.id_ibge)
        .outerjoin(mun_residencia, RegistroVacinacao.municipio_residencia_id == mun_residencia.id_ibge)
    )

    # Restrição automática de escopo para GESTOR_MUNICIPAL caso município não seja especificado
    if current_user.role == "GESTOR_MUNICIPAL" and current_user.municipio_alocado_id:
        if not municipio_id:
            municipio_id = current_user.municipio_alocado_id

    # Filtros
    if municipio_id:
        query = query.filter(
            or_(
                RegistroVacinacao.municipio_vacina_id == municipio_id,
                RegistroVacinacao.municipio_residencia_id == municipio_id,
            )
        )

    if vacina_id is not None:
        query = query.filter(RegistroVacinacao.vacina_id == vacina_id)

    if data_inicio:
        query = query.filter(RegistroVacinacao.data_vacinacao >= data_inicio)

    if data_fim:
        query = query.filter(RegistroVacinacao.data_vacinacao <= data_fim)

    if idade_min is not None:
        query = query.filter(RegistroVacinacao.idade >= idade_min)

    if idade_max is not None:
        query = query.filter(RegistroVacinacao.idade <= idade_max)

    if status_dado:
        query = query.filter(RegistroVacinacao.status_dado == status_dado)

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    results = (
        query.order_by(RegistroVacinacao.data_vacinacao.desc(), RegistroVacinacao.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for reg, vac_nome, mun_vac_nome, mun_res_nome in results:
        items.append(
            RegistroVacinacaoOut(
                id=reg.id,
                data_vacinacao=reg.data_vacinacao,
                idade=reg.idade,
                vacina_id=reg.vacina_id,
                vacina_nome=vac_nome,
                municipio_residencia_id=reg.municipio_residencia_id,
                municipio_residencia_nome=mun_res_nome,
                municipio_vacina_id=reg.municipio_vacina_id,
                municipio_vacina_nome=mun_vac_nome,
                teve_deslocamento=reg.teve_deslocamento,
                quantidade=reg.quantidade,
                status_dado=reg.status_dado,
            )
        )

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
    current_user: UsuarioAdmin = Depends(get_current_user),
):
    """RF07 - Cadastrar registro de vacinação manualmente fora da carga em lote do ETL."""
    # Validação do Município de Aplicação (Obrigatório)
    mun_vacina = db.query(Municipio).filter(Municipio.id_ibge == payload.municipio_vacina_id).first()
    if not mun_vacina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Município de aplicação não encontrado.",
        )

    # Validação do Município de Residência (Opcional)
    mun_residencia = None
    if payload.municipio_residencia_id:
        mun_residencia = db.query(Municipio).filter(Municipio.id_ibge == payload.municipio_residencia_id).first()
        if not mun_residencia:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Município de residência não encontrado.",
            )

    # Validação da Vacina (Opcional)
    vacina = None
    if payload.vacina_id is not None:
        vacina = db.query(Vacina).filter(Vacina.id == payload.vacina_id).first()
        if not vacina:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vacina não encontrada.",
            )

    # RN01: Cálculo automático de Deslocamento
    if payload.municipio_residencia_id is None:
        teve_deslocamento = None
    else:
        teve_deslocamento = payload.municipio_residencia_id != payload.municipio_vacina_id

    # RN02 & RN03: Cálculo automático de Status do Dado
    if payload.idade is not None and (payload.idade < 0 or payload.idade > 110):
        # RN03: Idade fora de 0-110 anos salva como DADO_INCONSISTENTE
        status_dado = "DADO_INCONSISTENTE"
    elif payload.municipio_residencia_id is None:
        # RN02: Sem residência -> DESLOCAMENTO_INDETERMINADO
        status_dado = "DESLOCAMENTO_INDETERMINADO"
    else:
        status_dado = "VALIDO"

    novo_registro = RegistroVacinacao(
        data_vacinacao=payload.data_vacinacao,
        idade=payload.idade,
        vacina_id=payload.vacina_id,
        municipio_residencia_id=payload.municipio_residencia_id,
        municipio_vacina_id=payload.municipio_vacina_id,
        teve_deslocamento=teve_deslocamento,
        quantidade=payload.quantidade,
        status_dado=status_dado,
    )

    db.add(novo_registro)
    db.commit()
    db.refresh(novo_registro)

    return RegistroVacinacaoOut(
        id=novo_registro.id,
        data_vacinacao=novo_registro.data_vacinacao,
        idade=novo_registro.idade,
        vacina_id=novo_registro.vacina_id,
        vacina_nome=vacina.nome if vacina else None,
        municipio_residencia_id=novo_registro.municipio_residencia_id,
        municipio_residencia_nome=mun_residencia.nome if mun_residencia else None,
        municipio_vacina_id=novo_registro.municipio_vacina_id,
        municipio_vacina_nome=mun_vacina.nome,
        teve_deslocamento=novo_registro.teve_deslocamento,
        quantidade=novo_registro.quantidade,
        status_dado=novo_registro.status_dado,
    )

