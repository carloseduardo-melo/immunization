"""RF19 - Exportação das listagens filtradas em CSV.

Cada endpoint aqui é o par de uma tela de listagem e aceita exatamente os mesmos
filtros do endpoint que alimenta aquela tela. Assim o arquivo baixado é sempre o
recorte que o gestor está vendo - só que inteiro, sem a paginação.

Os filtros não são reimplementados: cada endpoint reaproveita a montagem de
query do router de origem (`construir_query_*`, `_filtros_sql`) ou chama
diretamente a função que já calcula o painel. Duplicar a regra de filtro aqui
faria a exportação divergir da tela na primeira manutenção.
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.routers.alta_complexidade import obter_alta_complexidade
from app.routers.completude import construir_query_alertas
from app.routers.fluxo import _filtros_sql, consultar_pares_fluxo
from app.routers.municipios import construir_query_municipios
from app.routers.registros import construir_query_registros
from app.routers.vacinas import construir_query_vacinas
from app.services import exportacao
from app.services.exportacao import (
    cortar_no_limite,
    numero,
    resposta_csv,
    sim_nao,
    texto,
)
from app.sql_views import garantir_fluxo_atualizado

router = APIRouter(prefix="/exportacoes", tags=["Exportações"])

RESPOSTAS_CSV = {
    200: {
        "description": "Arquivo CSV do recorte filtrado.",
        "content": {"text/csv": {}},
    },
    401: {"description": "Token ausente ou inválido."},
}

# Mesmos rótulos exibidos nos badges da tela de registros.
ROTULOS_STATUS_DADO = {
    "VALIDO": "Válido",
    "DADO_INCONSISTENTE": "Dado inconsistente",
    "DESLOCAMENTO_INDETERMINADO": "Deslocamento indeterminado",
}

ROTULOS_STATUS_ALERTA = {
    "ABERTO": "Aberto",
    "INVESTIGANDO": "Investigando",
    "RESOLVIDO": "Resolvido",
    "FALSO_POSITIVO": "Falso positivo",
}


def _data(valor: Optional[date]) -> str:
    """Data no formato lido pelo Excel em português (e pela tela)."""
    return valor.strftime("%d/%m/%Y") if valor else exportacao.VAZIO


@router.get(
    "/registros",
    summary="Exportar registros de vacinação filtrados em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_registros(
    search: Optional[str] = None,
    municipio_id: Optional[str] = None,
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    idade_min: Optional[int] = None,
    idade_max: Optional[int] = None,
    status_dado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV os registros ativos do mesmo recorte de `GET /registros`."""
    query = construir_query_registros(
        db,
        search=search,
        municipio_id=municipio_id,
        vacina_id=vacina_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        idade_min=idade_min,
        idade_max=idade_max,
        status_dado=status_dado,
    )
    resultados, truncado = cortar_no_limite(
        query.limit(exportacao.limite_consulta()).all()
    )

    linhas = [
        [
            _data(registro.data_vacinacao),
            texto(municipio_vacina),
            texto(municipio_residencia),
            texto(vacina),
            texto(registro.idade),
            texto(registro.quantidade),
            sim_nao(registro.teve_deslocamento),
            ROTULOS_STATUS_DADO.get(registro.status_dado, texto(registro.status_dado)),
        ]
        for registro, municipio_vacina, municipio_residencia, vacina in resultados
    ]

    return resposta_csv(
        "registros.csv",
        [
            "Data",
            "Município de aplicação",
            "Município de residência",
            "Vacina",
            "Idade",
            "Quantidade",
            "Houve deslocamento",
            "Status do dado",
        ],
        linhas,
        truncado,
    )


@router.get(
    "/municipios",
    summary="Exportar municípios filtrados em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_municipios(
    uf: Optional[str] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV os municípios do mesmo recorte de `GET /municipios`."""
    query = construir_query_municipios(db, uf=uf, ativo=ativo, search=search)
    municipios, truncado = cortar_no_limite(
        query.limit(exportacao.limite_consulta()).all()
    )

    linhas = [
        [
            municipio.id_ibge,
            municipio.nome,
            municipio.uf,
            texto(municipio.regiao_saude),
            sim_nao(municipio.polo),
            sim_nao(municipio.ativo),
        ]
        for municipio in municipios
    ]

    return resposta_csv(
        "municipios.csv",
        ["Código IBGE", "Nome", "UF", "Região de saúde", "Município-polo", "Ativo"],
        linhas,
        truncado,
    )


@router.get(
    "/vacinas",
    summary="Exportar vacinas filtradas em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_vacinas(
    alta_complexidade: Optional[bool] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV as vacinas do mesmo recorte de `GET /vacinas`."""
    query = construir_query_vacinas(
        db, alta_complexidade=alta_complexidade, ativo=ativo, search=search
    )
    vacinas, truncado = cortar_no_limite(
        query.limit(exportacao.limite_consulta()).all()
    )

    linhas = [
        [
            vacina.id,
            vacina.nome,
            sim_nao(vacina.alta_complexidade),
            sim_nao(vacina.ativo),
        ]
        for vacina in vacinas
    ]

    return resposta_csv(
        "vacinas.csv",
        ["ID", "Nome", "Alta complexidade", "Ativo"],
        linhas,
        truncado,
    )


@router.get(
    "/fluxo",
    summary="Exportar fluxo intermunicipal filtrado em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_fluxo(
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    municipio_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV os pares origem/destino do mesmo recorte de
    `GET /fluxo/intermunicipal`, sem o corte de página."""
    garantir_fluxo_atualizado(db)
    where_sql, params = _filtros_sql(vacina_id, data_inicio, data_fim, municipio_id)
    pares, truncado = cortar_no_limite(
        consultar_pares_fluxo(db, where_sql, params, limite=exportacao.limite_consulta())
    )

    linhas = [
        [
            par["municipio_origem_nome"],
            par["municipio_destino_nome"],
            int(par["total_doses"]),
        ]
        for par in pares
    ]

    return resposta_csv(
        "fluxo-intermunicipal.csv",
        [
            "Município de origem (residência)",
            "Município de destino (aplicação)",
            "Doses",
        ],
        linhas,
        truncado,
    )


@router.get(
    "/completude",
    summary="Exportar alertas de completude filtrados em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_completude(
    status: Optional[
        Literal["ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"]
    ] = None,
    municipio_id: Optional[str] = None,
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV os alertas do mesmo recorte de `GET /completude/alertas`.

    O recorte do gestor municipal é aplicado pela mesma função que a listagem
    usa, então o arquivo nunca sai do município vinculado ao perfil."""
    _, query = construir_query_alertas(
        db, current_user, status=status, municipio_id=municipio_id, ano=ano
    )
    alertas, truncado = cortar_no_limite(
        query.limit(exportacao.limite_consulta()).all()
    )

    linhas = [
        [
            f"{alerta.referencia_mes:02d}/{alerta.referencia_ano}",
            texto(alerta.municipio.nome if alerta.municipio else None),
            alerta.total_observado,
            ROTULOS_STATUS_ALERTA.get(alerta.status, texto(alerta.status)),
            alerta.criado_em.strftime("%d/%m/%Y %H:%M") if alerta.criado_em else exportacao.VAZIO,
        ]
        for alerta in alertas
    ]

    return resposta_csv(
        "alertas-completude.csv",
        ["Referência", "Município", "Total observado", "Status", "Criado em"],
        linhas,
        truncado,
    )


@router.get(
    "/alta-complexidade",
    summary="Exportar o painel de alta complexidade em CSV",
    responses=RESPOSTAS_CSV,
)
def exportar_alta_complexidade(
    top_municipios: int = 3,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF19 - Baixa em CSV o painel de `GET /alta-complexidade`.

    O painel é hierárquico (uma vacina, vários municípios de aplicação); o CSV o
    achata em uma linha por município, repetindo os números da vacina. Vacina sem
    nenhuma aplicação sai numa linha só, com as colunas de município vazias -
    esconder essas vacinas tiraria da vista justamente o caso a investigar."""
    painel = obter_alta_complexidade(
        top_municipios=top_municipios, db=db, current_user=current_user
    )

    linhas = []
    for vacina in painel.items:
        base = [
            vacina.vacina_nome,
            vacina.total_doses,
            vacina.total_deslocamentos,
            vacina.total_indeterminado,
            numero(vacina.taxa_deslocamento),
            texto(vacina.centro_referencia_nome),
        ]
        if not vacina.municipios:
            linhas.append(base + [texto(None), texto(None), texto(None)])
            continue
        for municipio in vacina.municipios:
            linhas.append(
                base
                + [
                    municipio.municipio_nome,
                    municipio.total_doses,
                    numero(municipio.percentual),
                ]
            )

    return resposta_csv(
        "alta-complexidade.csv",
        [
            "Vacina",
            "Total de doses",
            "Doses deslocadas",
            "Doses de origem indeterminada",
            "Taxa de deslocamento (%)",
            "Centro de referência",
            "Município de aplicação",
            "Doses no município",
            "% do total da vacina",
        ],
        linhas,
    )
