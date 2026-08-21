"""RF18 - Painel de imunobiológicos de alta complexidade.

Para cada vacina marcada com `alta_complexidade`, mostra a taxa de deslocamento
e os municípios de maior volume de aplicação - o primeiro deles é o centro de
referência regional.

A base de cálculo (registros ativos, exceto DADO_INCONSISTENTE) é a mesma do
`taxa_mobilidade` de /dashboard/resumo, para os dois painéis não se
contradizerem. A `mv_fluxo_intermunicipal` não serve aqui: ela só contém
registros com deslocamento real, e a taxa precisa do denominador completo.
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Municipio, RegistroVacinacao, Vacina
from app.schemas import (
    AltaComplexidadeResponse,
    MunicipioAplicacaoItem,
    VacinaAltaComplexidadeItem,
)

router = APIRouter(prefix="/alta-complexidade", tags=["Alta Complexidade"])

TOP_MUNICIPIOS_PADRAO = 3
TOP_MUNICIPIOS_MAXIMO = 10


def _base_valida(db: Session, ids_vacinas: list[int]):
    """Registros que entram em todos os números desta tela."""
    return db.query(RegistroVacinacao).filter(
        RegistroVacinacao.ativo == True,
        RegistroVacinacao.status_dado != "DADO_INCONSISTENTE",
        RegistroVacinacao.vacina_id.in_(ids_vacinas),
    )


@router.get(
    "",
    response_model=AltaComplexidadeResponse,
    summary="Vacinas de alta complexidade e seus centros de referência",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_alta_complexidade(
    top_municipios: int = TOP_MUNICIPIOS_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF18 - Lista as vacinas com `alta_complexidade = true` e `ativo = true`,
    da maior para a menor em volume de doses, com a taxa de deslocamento de cada
    uma e o ranking dos municípios de maior aplicação.

    Vacina de alta complexidade sem nenhum registro aparece zerada: escondê-la
    tiraria da vista justamente o caso que o gestor precisa investigar."""
    if top_municipios < 1:
        top_municipios = TOP_MUNICIPIOS_PADRAO
    if top_municipios > TOP_MUNICIPIOS_MAXIMO:
        top_municipios = TOP_MUNICIPIOS_MAXIMO

    vacinas = (
        db.query(Vacina)
        .filter(Vacina.alta_complexidade == True, Vacina.ativo == True)
        .all()
    )
    if not vacinas:
        return AltaComplexidadeResponse(items=[], total_vacinas=0)

    ids = [vacina.id for vacina in vacinas]

    totais = dict(
        _base_valida(db, ids)
        .with_entities(
            RegistroVacinacao.vacina_id,
            func.sum(RegistroVacinacao.quantidade),
        )
        .group_by(RegistroVacinacao.vacina_id)
        .all()
    )
    deslocamentos = dict(
        _base_valida(db, ids)
        .filter(RegistroVacinacao.teve_deslocamento == True)
        .with_entities(
            RegistroVacinacao.vacina_id,
            func.sum(RegistroVacinacao.quantidade),
        )
        .group_by(RegistroVacinacao.vacina_id)
        .all()
    )

    # Uma linha por (vacina, município), já ordenada por volume: o corte do
    # top N acontece em Python sobre este agregado, que é pequeno - são poucas
    # vacinas de alta complexidade. Window function não roda igual no SQLite.
    linhas_municipios = (
        _base_valida(db, ids)
        .join(Municipio, Municipio.id_ibge == RegistroVacinacao.municipio_vacina_id)
        .with_entities(
            RegistroVacinacao.vacina_id.label("vacina_id"),
            RegistroVacinacao.municipio_vacina_id.label("municipio_id"),
            Municipio.nome.label("municipio_nome"),
            func.sum(RegistroVacinacao.quantidade).label("total"),
        )
        .group_by(
            RegistroVacinacao.vacina_id,
            RegistroVacinacao.municipio_vacina_id,
            Municipio.nome,
        )
        .order_by(func.sum(RegistroVacinacao.quantidade).desc())
        .all()
    )
    por_vacina = defaultdict(list)
    for linha in linhas_municipios:
        por_vacina[linha.vacina_id].append(linha)

    items = []
    for vacina in vacinas:
        total = int(totais.get(vacina.id) or 0)
        deslocados = int(deslocamentos.get(vacina.id) or 0)
        municipios = [
            MunicipioAplicacaoItem(
                municipio_id=linha.municipio_id,
                municipio_nome=linha.municipio_nome,
                total_doses=int(linha.total),
                percentual=round(int(linha.total) / total * 100, 2),
            )
            for linha in por_vacina[vacina.id][:top_municipios]
        ]
        items.append(
            VacinaAltaComplexidadeItem(
                vacina_id=vacina.id,
                vacina_nome=vacina.nome,
                total_doses=total,
                total_deslocamentos=deslocados,
                taxa_deslocamento=round(deslocados / total * 100, 2) if total else 0.0,
                centro_referencia_id=municipios[0].municipio_id if municipios else None,
                centro_referencia_nome=municipios[0].municipio_nome if municipios else None,
                municipios=municipios,
            )
        )

    items.sort(key=lambda item: (-item.total_doses, item.vacina_nome))
    return AltaComplexidadeResponse(items=items, total_vacinas=len(items))
