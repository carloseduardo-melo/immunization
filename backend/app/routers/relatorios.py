"""RF20 - Relatório consolidado em PDF de cada painel.

Um endpoint por tela, com os mesmos filtros do endpoint que a alimenta - a mesma
regra do RF19, e pelo mesmo motivo: o documento levado a uma prestação de contas
precisa ser exatamente o recorte que o gestor estava vendo.

Os filtros não são reimplementados aqui; cada endpoint reaproveita a montagem de
query do router de origem (`construir_query_*`, `_filtros_sql`). O que este
módulo acrescenta é a tradução do recorte para o documento: o rótulo legível de
cada filtro, as colunas da tabela e, quando o painel tem um gráfico, a série que
o reproduz.
"""

from collections import Counter
from datetime import date
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Municipio, Vacina
from app.routers.alta_complexidade import obter_alta_complexidade
from app.routers.completude import construir_query_alertas
from app.routers.exportacoes import ROTULOS_STATUS_ALERTA, ROTULOS_STATUS_DADO
from app.routers.fluxo import _filtros_sql, consultar_pares_fluxo
from app.routers.municipios import construir_query_municipios
from app.routers.registros import construir_query_registros
from app.routers.vacinas import construir_query_vacinas
from app.services import relatorio_pdf
from app.services.relatorio_pdf import cortar_no_limite, resposta_pdf, texto
from app.sql_views import garantir_fluxo_atualizado

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

RESPOSTAS_PDF = {
    200: {
        "description": "Relatório do painel em PDF.",
        "content": {"application/pdf": {}},
    },
    401: {"description": "Token ausente ou inválido."},
}

TODOS = "Todos"
TODAS = "Todas"

# Barras no gráfico do fluxo: acima disto os rótulos "origem → destino" viram
# uma faixa ilegível no eixo.
TOP_GRAFICO = 10


def _numero(valor: Any) -> str:
    """Decimal com vírgula, como no CSV e como o gestor lê."""
    return str(valor).replace(".", ",")


def _data(valor: Optional[date]) -> str:
    return valor.strftime("%d/%m/%Y") if valor else relatorio_pdf.VAZIO


def _periodo(data_inicio: Optional[date], data_fim: Optional[date]) -> str:
    """Recorte temporal em uma frase, mesmo quando só um dos lados foi informado."""
    if data_inicio and data_fim:
        return f"{_data(data_inicio)} a {_data(data_fim)}"
    if data_inicio:
        return f"a partir de {_data(data_inicio)}"
    if data_fim:
        return f"até {_data(data_fim)}"
    return "Todo o período"


def _nome_municipio(db: Session, id_ibge: Optional[str]) -> str:
    """Nome do município do filtro: o código IBGE sozinho não diz nada ao leitor."""
    if not id_ibge:
        return TODOS
    municipio = db.query(Municipio).filter(Municipio.id_ibge == id_ibge).first()
    return f"{municipio.nome} ({id_ibge})" if municipio else id_ibge


def _nome_vacina(db: Session, vacina_id: Optional[int]) -> str:
    if vacina_id is None:
        return TODAS
    vacina = db.query(Vacina).filter(Vacina.id == vacina_id).first()
    return vacina.nome if vacina else str(vacina_id)


def _sim_nao(valor: Any) -> str:
    return "Sim" if valor else "Não"


def _situacao(ativo: Optional[bool]) -> str:
    if ativo is None:
        return "Ativos e inativos"
    return "Somente ativos" if ativo else "Somente inativos"


def _complexidade(alta_complexidade: Optional[bool]) -> str:
    if alta_complexidade is None:
        return TODAS
    return "Somente alta complexidade" if alta_complexidade else "Somente padrão"


def _faixa(minimo: Optional[int], maximo: Optional[int], sufixo: str) -> str:
    if minimo is None and maximo is None:
        return TODAS
    if minimo is not None and maximo is not None:
        return f"{minimo} a {maximo} {sufixo}"
    if minimo is not None:
        return f"a partir de {minimo} {sufixo}"
    return f"até {maximo} {sufixo}"


@router.get(
    "/registros",
    summary="Relatório em PDF dos registros de vacinação filtrados",
    responses=RESPOSTAS_PDF,
)
def relatorio_registros(
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
    """RF20 - Relatório do mesmo recorte de `GET /registros`, em PDF."""
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
    total = query.count()
    resultados, truncado = cortar_no_limite(
        query.limit(relatorio_pdf.LIMITE_LINHAS + 1).all()
    )

    linhas = [
        [
            _data(registro.data_vacinacao),
            texto(municipio_vacina),
            texto(municipio_residencia),
            texto(vacina),
            texto(registro.idade),
            texto(registro.quantidade),
            ROTULOS_STATUS_DADO.get(registro.status_dado, texto(registro.status_dado)),
        ]
        for registro, municipio_vacina, municipio_residencia, vacina in resultados
    ]

    return resposta_pdf(
        "registros.pdf",
        "Registros de vacinação",
        current_user.email,
        [
            ("Município", _nome_municipio(db, municipio_id)),
            ("Vacina", _nome_vacina(db, vacina_id)),
            ("Período", _periodo(data_inicio, data_fim)),
            ("Faixa etária", _faixa(idade_min, idade_max, "anos")),
            ("Status do dado", ROTULOS_STATUS_DADO.get(status_dado, TODOS)),
            ("Busca", texto(search) if search else "—"),
        ],
        [
            "Data",
            "Município de aplicação",
            "Município de residência",
            "Vacina",
            "Idade",
            "Quantidade",
            "Status do dado",
        ],
        linhas,
        total,
        truncado,
    )


@router.get(
    "/municipios",
    summary="Relatório em PDF dos municípios cadastrados",
    responses=RESPOSTAS_PDF,
)
def relatorio_municipios(
    uf: Optional[str] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF20 - Relatório do mesmo recorte de `GET /municipios`, em PDF."""
    query = construir_query_municipios(db, uf=uf, ativo=ativo, search=search)
    total = query.count()
    municipios, truncado = cortar_no_limite(
        query.limit(relatorio_pdf.LIMITE_LINHAS + 1).all()
    )

    linhas = [
        [
            municipio.id_ibge,
            municipio.nome,
            municipio.uf,
            texto(municipio.regiao_saude),
            _sim_nao(municipio.polo),
            _sim_nao(municipio.ativo),
        ]
        for municipio in municipios
    ]

    return resposta_pdf(
        "municipios.pdf",
        "Municípios cadastrados",
        current_user.email,
        [
            ("UF", uf.upper() if uf else TODAS),
            ("Situação", _situacao(ativo)),
            ("Busca", texto(search) if search else "—"),
        ],
        ["Código IBGE", "Nome", "UF", "Região de saúde", "Município-polo", "Ativo"],
        linhas,
        total,
        truncado,
        vazio="Nenhum município encontrado para os filtros aplicados.",
    )


@router.get(
    "/vacinas",
    summary="Relatório em PDF das vacinas cadastradas",
    responses=RESPOSTAS_PDF,
)
def relatorio_vacinas(
    alta_complexidade: Optional[bool] = None,
    ativo: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF20 - Relatório do mesmo recorte de `GET /vacinas`, em PDF."""
    query = construir_query_vacinas(
        db, alta_complexidade=alta_complexidade, ativo=ativo, search=search
    )
    total = query.count()
    vacinas, truncado = cortar_no_limite(
        query.limit(relatorio_pdf.LIMITE_LINHAS + 1).all()
    )

    linhas = [
        [
            vacina.id,
            vacina.nome,
            _sim_nao(vacina.alta_complexidade),
            _sim_nao(vacina.ativo),
        ]
        for vacina in vacinas
    ]

    return resposta_pdf(
        "vacinas.pdf",
        "Vacinas cadastradas",
        current_user.email,
        [
            ("Complexidade", _complexidade(alta_complexidade)),
            ("Situação", _situacao(ativo)),
            ("Busca", texto(search) if search else "—"),
        ],
        ["ID", "Nome", "Alta complexidade", "Ativo"],
        linhas,
        total,
        truncado,
        vazio="Nenhuma vacina encontrada para os filtros aplicados.",
    )


@router.get(
    "/fluxo",
    summary="Relatório em PDF do fluxo intermunicipal filtrado",
    responses=RESPOSTAS_PDF,
)
def relatorio_fluxo(
    vacina_id: Optional[int] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    municipio_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF20 - Relatório do mesmo recorte de `GET /fluxo/intermunicipal`, em PDF."""
    garantir_fluxo_atualizado(db)
    where_sql, params = _filtros_sql(vacina_id, data_inicio, data_fim, municipio_id)
    pares, truncado = cortar_no_limite(
        consultar_pares_fluxo(
            db, where_sql, params, limite=relatorio_pdf.LIMITE_LINHAS + 1
        )
    )

    linhas = [
        [
            par["municipio_origem_nome"],
            par["municipio_destino_nome"],
            int(par["total_doses"]),
        ]
        for par in pares
    ]

    # Os pares já vêm do maior fluxo para o menor: o gráfico é o topo dessa
    # mesma ordenação, o que a tela chama de "mapa de calor dos maiores fluxos".
    grafico = None
    if linhas:
        topo = linhas[:TOP_GRAFICO]
        grafico = (
            "Maiores fluxos do recorte",
            [f"{origem} → {destino}" for origem, destino, _ in topo],
            [doses for _, _, doses in topo],
        )

    return resposta_pdf(
        "fluxo-intermunicipal.pdf",
        "Fluxo intermunicipal",
        current_user.email,
        [
            ("Vacina", _nome_vacina(db, vacina_id)),
            ("Período", _periodo(data_inicio, data_fim)),
            ("Município (origem ou destino)", _nome_municipio(db, municipio_id)),
        ],
        [
            "Município de origem (residência)",
            "Município de destino (aplicação)",
            "Doses",
        ],
        linhas,
        len(linhas),
        truncado,
        vazio="Nenhum deslocamento encontrado para os filtros aplicados.",
        grafico=grafico,
    )


@router.get(
    "/completude",
    summary="Relatório em PDF dos alertas de completude filtrados",
    responses=RESPOSTAS_PDF,
)
def relatorio_completude(
    status: Optional[
        Literal["ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"]
    ] = None,
    municipio_id: Optional[str] = None,
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF20 - Relatório do mesmo recorte de `GET /completude/alertas`, em PDF.

    O escopo do gestor municipal vem da mesma função da listagem, então o
    documento nunca sai do município vinculado ao perfil."""
    _, query = construir_query_alertas(
        db, current_user, status=status, municipio_id=municipio_id, ano=ano
    )
    total = query.count()
    alertas, truncado = cortar_no_limite(
        query.limit(relatorio_pdf.LIMITE_LINHAS + 1).all()
    )

    linhas = [
        [
            f"{alerta.referencia_mes:02d}/{alerta.referencia_ano}",
            texto(alerta.municipio.nome if alerta.municipio else None),
            alerta.total_observado,
            ROTULOS_STATUS_ALERTA.get(alerta.status, texto(alerta.status)),
        ]
        for alerta in alertas
    ]

    # A distribuição por status é a leitura de gestão do painel: quantos alertas
    # ainda estão abertos contra quantos já foram tratados.
    grafico = None
    if linhas:
        contagem = Counter(alerta.status for alerta in alertas)
        grafico = (
            "Alertas por status",
            [ROTULOS_STATUS_ALERTA[chave] for chave in ROTULOS_STATUS_ALERTA],
            [contagem.get(chave, 0) for chave in ROTULOS_STATUS_ALERTA],
        )

    return resposta_pdf(
        "alertas-completude.pdf",
        "Alertas de completude",
        current_user.email,
        [
            ("Status", ROTULOS_STATUS_ALERTA.get(status, TODOS)),
            ("Município", _nome_municipio(db, municipio_id)),
            ("Ano de referência", texto(ano) if ano else "Todos os anos"),
        ],
        ["Referência", "Município", "Total observado", "Status"],
        linhas,
        total,
        truncado,
        vazio="Nenhum alerta de completude para os filtros aplicados.",
        grafico=grafico,
    )


@router.get(
    "/alta-complexidade",
    summary="Relatório em PDF do painel de alta complexidade",
    responses=RESPOSTAS_PDF,
)
def relatorio_alta_complexidade(
    top_municipios: int = 3,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF20 - Relatório do painel de `GET /alta-complexidade`, em PDF.

    A tabela repete os números da vacina em cada município de aplicação, como no
    CSV; o gráfico resume o painel em uma barra por vacina."""
    painel = obter_alta_complexidade(
        top_municipios=top_municipios, db=db, current_user=current_user
    )

    linhas = []
    for vacina in painel.items:
        base = [
            vacina.vacina_nome,
            vacina.total_doses,
            vacina.total_deslocamentos,
            _numero(vacina.taxa_deslocamento),
            texto(vacina.centro_referencia_nome),
        ]
        if not vacina.municipios:
            linhas.append(base + [texto(None), texto(None)])
            continue
        for municipio in vacina.municipios:
            linhas.append(
                base + [municipio.municipio_nome, municipio.total_doses]
            )

    grafico = None
    if painel.items:
        grafico = (
            "Doses por vacina",
            [vacina.vacina_nome for vacina in painel.items],
            [vacina.total_doses for vacina in painel.items],
        )

    return resposta_pdf(
        "alta-complexidade.pdf",
        "Imunobiológicos de alta complexidade",
        current_user.email,
        [("Municípios por vacina", f"Top {top_municipios}")],
        [
            "Vacina",
            "Total de doses",
            "Doses deslocadas",
            "Taxa de deslocamento (%)",
            "Centro de referência",
            "Município de aplicação",
            "Doses no município",
        ],
        linhas,
        len(linhas),
        False,
        vazio="Nenhuma vacina de alta complexidade encontrada.",
        grafico=grafico,
    )
