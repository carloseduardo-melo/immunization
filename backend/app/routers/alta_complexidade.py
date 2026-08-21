"""RF18 - Painel de imunobiológicos de alta complexidade.

Para cada vacina marcada com `alta_complexidade`, mostra a taxa de deslocamento
e os municípios de maior volume de aplicação - o primeiro deles é o centro de
referência regional.

A base de cálculo exclui DADO_INCONSISTENTE tanto do numerador (doses
deslocadas) quanto do denominador (total de doses) - a estatística mais
defensável para este painel. Isso difere do `taxa_mobilidade` de
/dashboard/resumo, que usa base mista (denominador com inconsistentes,
numerador sem); por isso a taxa de deslocamento aqui pode divergir da taxa de
mobilidade do Dashboard para a mesma vacina - é decisão de projeto, não bug.
A `mv_fluxo_intermunicipal` não serve aqui: ela só contém registros com
deslocamento real, e a taxa precisa do denominador completo.

`total_doses` continua contando toda a base válida, incluindo os registros sem
município de residência (`teve_deslocamento IS NULL`, ETL marca como
DESLOCAMENTO_INDETERMINADO) - volume aplicado é volume aplicado, e o ranking de
municípios depende desse total. Mas esses registros nunca podem entrar no
numerador (`teve_deslocamento == True` descarta NULL), então deixá-los no
denominador de `taxa_deslocamento` dilui a taxa de forma desigual entre
vacinas e municípios, conforme a fatia de origem desconhecida de cada um. Por
isso `taxa_deslocamento` usa como denominador `total_doses - total_indeterminado`
(as doses de origem conhecida): "das doses cuja origem conhecemos, quantas
foram deslocadas". `total_indeterminado` também é exposto por vacina.
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
    # Origem desconhecida: teve_deslocamento IS NULL e o criterio exato (nao
    # status_dado) porque e o que garante, por construcao, que este numero seja
    # subconjunto de `totais` - o denominador de taxa_deslocamento depende disso.
    indeterminados = dict(
        _base_valida(db, ids)
        .filter(RegistroVacinacao.teve_deslocamento.is_(None))
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
        # Empate resolvido pelo menor id de municipio, para a resposta ser
        # deterministica - o RF17 faz o analogo com o numero do mes.
        .order_by(
            func.sum(RegistroVacinacao.quantidade).desc(),
            RegistroVacinacao.municipio_vacina_id.asc(),
        )
        .all()
    )
    por_vacina = defaultdict(list)
    for linha in linhas_municipios:
        por_vacina[linha.vacina_id].append(linha)

    items = []
    for vacina in vacinas:
        total = int(totais.get(vacina.id) or 0)
        deslocados = int(deslocamentos.get(vacina.id) or 0)
        indeterminado = int(indeterminados.get(vacina.id) or 0)
        base_conhecida = total - indeterminado
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
                total_indeterminado=indeterminado,
                taxa_deslocamento=(
                    round(deslocados / base_conhecida * 100, 2)
                    if base_conhecida
                    else 0.0
                ),
                centro_referencia_id=municipios[0].municipio_id if municipios else None,
                centro_referencia_nome=municipios[0].municipio_nome if municipios else None,
                municipios=municipios,
            )
        )

    items.sort(key=lambda item: (-item.total_doses, item.vacina_nome))
    return AltaComplexidadeResponse(items=items, total_vacinas=len(items))
