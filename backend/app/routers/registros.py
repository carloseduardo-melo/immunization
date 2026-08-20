from datetime import date
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.dependencies import get_current_user
from app.models import LogAuditoria, Municipio, RegistroVacinacao, Vacina
from app.schemas import (
    PaginatedRegistros,
    RegistroVacinacaoCreate,
    RegistroVacinacaoOut,
    RegistroVacinacaoUpdate,
)
from app.sql_views import marcar_fluxo_desatualizado

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
        .filter(RegistroVacinacao.id == id, RegistroVacinacao.ativo == True)
        .first()
    )
    if not registro:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro de vacinação não encontrado ou inativo.",
        )
    return registro


def _buscar_municipio(db: Session, id_ibge: str) -> Municipio:
    municipio = db.query(Municipio).filter(Municipio.id_ibge == id_ibge).first()
    if not municipio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Município de aplicação não encontrado.",
        )
    return municipio


@router.get(
    "",
    response_model=PaginatedRegistros,
    summary="Listar registros de vacinação",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def listar_registros(
    search: Optional[str] = None,
    municipio_id: Optional[str] = None,
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    idade_min: Optional[int] = None,
    idade_max: Optional[int] = None,
    status_dado: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista e pagina os registros de vacinação ativos, incluindo nomes dos municípios e vacinas.

    Suporta filtros combináveis por município (residência ou aplicação),
    vacina, faixa de data, faixa de idade e status do dado."""
    if page < 1: page = 1
    if page_size < 1: page_size = 10
    # Teto igual ao de /municipios e /vacinas: sem ele, um page_size grande
    # traria centenas de milhares de registros numa única resposta.
    if page_size > 100: page_size = 100

    MunicipioResidencia = aliased(Municipio)

    # Inicia a query filtrando apenas registros ativos (RN05)
    query = db.query(
        RegistroVacinacao,
        Municipio.nome.label("municipio_vacina_nome"),
        MunicipioResidencia.nome.label("municipio_residencia_nome"),
        Vacina.nome.label("vacina_nome")
    ).outerjoin(
        Municipio, RegistroVacinacao.municipio_vacina_id == Municipio.id_ibge
    ).outerjoin(
        MunicipioResidencia, RegistroVacinacao.municipio_residencia_id == MunicipioResidencia.id_ibge
    ).outerjoin(
        Vacina, RegistroVacinacao.vacina_id == Vacina.id
    ).filter(RegistroVacinacao.ativo == True)

    if search:
        query = query.filter(
            Municipio.nome.ilike(f"%{search}%") | Vacina.nome.ilike(f"%{search}%")
        )

    if municipio_id:
        query = query.filter(
            (RegistroVacinacao.municipio_residencia_id == municipio_id)
            | (RegistroVacinacao.municipio_vacina_id == municipio_id)
        )

    if vacina_id is not None:
        query = query.filter(RegistroVacinacao.vacina_id == vacina_id)

    if data_inicio is not None:
        query = query.filter(RegistroVacinacao.data_vacinacao >= data_inicio)

    if data_fim is not None:
        query = query.filter(RegistroVacinacao.data_vacinacao <= data_fim)

    if idade_min is not None:
        query = query.filter(RegistroVacinacao.idade >= idade_min)

    if idade_max is not None:
        query = query.filter(RegistroVacinacao.idade <= idade_max)

    if status_dado:
        query = query.filter(RegistroVacinacao.status_dado == status_dado)

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0

    resultados = (
        query.order_by(RegistroVacinacao.data_vacinacao.desc(), RegistroVacinacao.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for reg, mun_vacina_nome, mun_residencia_nome, vac_nome in resultados:
        reg_dict = {c.name: getattr(reg, c.name) for c in reg.__table__.columns}
        reg_dict["municipio_vacina_nome"] = mun_vacina_nome
        reg_dict["municipio_residencia_nome"] = mun_residencia_nome
        reg_dict["vacina_nome"] = vac_nome
        items.append(reg_dict)

    return PaginatedRegistros(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=RegistroVacinacaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar registro de vacinação",
    responses={
        401: {"description": "Token ausente ou inválido."},
        404: {"description": "Município de aplicação (ou de residência) não encontrado."},
    },
)
def criar_registro(
    payload: RegistroVacinacaoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cria um novo registro manual de vacinação.

    Calcula automaticamente `teve_deslocamento` (comparando município de
    residência e de aplicação) e `status_dado`: `DADO_INCONSISTENTE` se a
    idade estiver fora de 0-110, `DESLOCAMENTO_INDETERMINADO` se o
    município de residência não for informado, ou `VALIDO` caso contrário."""
    municipio_vacina = _buscar_municipio(db, payload.municipio_vacina_id)
    municipio_residencia = (
        _buscar_municipio(db, payload.municipio_residencia_id)
        if payload.municipio_residencia_id
        else None
    )
    vacina = (
        db.query(Vacina).filter(Vacina.id == payload.vacina_id).first()
        if payload.vacina_id is not None
        else None
    )

    teve_deslocamento = None
    if payload.municipio_residencia_id:
        teve_deslocamento = payload.municipio_residencia_id != payload.municipio_vacina_id

    if payload.idade is not None and (payload.idade < 0 or payload.idade > 110):
        status_calculado = "DADO_INCONSISTENTE"
    elif not payload.municipio_residencia_id:
        status_calculado = "DESLOCAMENTO_INDETERMINADO"
    else:
        status_calculado = "VALIDO"

    novo_registro = RegistroVacinacao(
        data_vacinacao=payload.data_vacinacao,
        municipio_vacina_id=payload.municipio_vacina_id,
        municipio_residencia_id=payload.municipio_residencia_id,
        vacina_id=payload.vacina_id,
        idade=payload.idade,
        quantidade=payload.quantidade,
        status_dado=status_calculado,
        teve_deslocamento=teve_deslocamento,
        ativo=True,
    )

    db.add(novo_registro)
    db.commit()
    db.refresh(novo_registro)
    marcar_fluxo_desatualizado(db)
    db.commit()

    return RegistroVacinacaoOut(
        id=novo_registro.id,
        data_vacinacao=novo_registro.data_vacinacao,
        idade=novo_registro.idade,
        vacina_id=novo_registro.vacina_id,
        vacina_nome=vacina.nome if vacina else None,
        municipio_residencia_id=novo_registro.municipio_residencia_id,
        municipio_residencia_nome=municipio_residencia.nome if municipio_residencia else None,
        municipio_vacina_id=novo_registro.municipio_vacina_id,
        municipio_vacina_nome=municipio_vacina.nome,
        teve_deslocamento=novo_registro.teve_deslocamento,
        quantidade=novo_registro.quantidade,
        status_dado=novo_registro.status_dado,
    )


@router.put(
    "/{id}",
    response_model=RegistroVacinacaoOut,
    summary="Editar (retificar) registro de vacinação",
    responses={
        401: {"description": "Token ausente ou inválido."},
        404: {"description": "Registro (ou município informado) não encontrado, ou registro inativo."},
    },
)
def atualizar_registro(
    id: UUID,
    payload: RegistroVacinacaoUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF08 - Edita (retifica) um registro ativo existente, recalcula `teve_deslocamento`/`status_dado`
    e grava um log de auditoria com os valores antigos e novos."""
    registro = _buscar_registro_ativo(db, id)
    valores_antigos = _registro_para_auditoria(registro)

    teve_deslocamento = None
    if payload.municipio_residencia_id:
        teve_deslocamento = payload.municipio_residencia_id != payload.municipio_vacina_id

    if payload.idade is not None and (payload.idade < 0 or payload.idade > 110):
        status_calculado = "DADO_INCONSISTENTE"
    elif not payload.municipio_residencia_id:
        status_calculado = "DESLOCAMENTO_INDETERMINADO"
    else:
        status_calculado = "VALIDO"

    registro.data_vacinacao = payload.data_vacinacao
    registro.municipio_vacina_id = payload.municipio_vacina_id
    registro.municipio_residencia_id = payload.municipio_residencia_id
    registro.vacina_id = payload.vacina_id
    registro.idade = payload.idade
    registro.quantidade = payload.quantidade
    registro.status_dado = status_calculado
    registro.teve_deslocamento = teve_deslocamento

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
    marcar_fluxo_desatualizado(db)
    db.commit()

    mun_vac = _buscar_municipio(db, registro.municipio_vacina_id)
    mun_res = _buscar_municipio(db, registro.municipio_residencia_id) if registro.municipio_residencia_id else None
    vac = db.query(Vacina).filter(Vacina.id == registro.vacina_id).first() if registro.vacina_id else None

    return RegistroVacinacaoOut(
        id=registro.id,
        data_vacinacao=registro.data_vacinacao,
        idade=registro.idade,
        vacina_id=registro.vacina_id,
        vacina_nome=vac.nome if vac else None,
        municipio_residencia_id=registro.municipio_residencia_id,
        municipio_residencia_nome=mun_res.nome if mun_res else None,
        municipio_vacina_id=registro.municipio_vacina_id,
        municipio_vacina_nome=mun_vac.nome,
        teve_deslocamento=registro.teve_deslocamento,
        quantidade=registro.quantidade,
        status_dado=registro.status_dado,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir (logicamente) registro de vacinação",
    responses={
        401: {"description": "Token ausente ou inválido."},
        404: {"description": "Registro não encontrado ou já inativo."},
    },
)
def excluir_registro(
    id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Exclui logicamente um registro (`ativo=false`) e grava um log de auditoria da exclusão.
    O registro permanece fisicamente no banco, mas deixa de aparecer nas listagens."""
    registro = _buscar_registro_ativo(db, id)
    valores_antigos = _registro_para_auditoria(registro)

    # Exclusão Lógica implementada aqui (RN05)
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
    marcar_fluxo_desatualizado(db)
    db.commit()

    return None
