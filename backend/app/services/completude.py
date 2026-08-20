"""RF15 - Detecção de meses/municípios com volume de registros fora do padrão.

A faixa esperada de cada município vem do histórico dele mesmo:
`limite_inferior = média - k * desvio_padrão` sobre os totais mensais. Só o lado
inferior gera alerta — o requisito trata de dado faltando, e um pico acima da
média é mutirão de vacinação, não falha de completude.

A agregação por (município, ano, mês) acontece no banco, reduzindo milhões de
registros a alguns milhares de linhas; média e desvio são calculados em Python
porque o SQLite (usado nos testes) não tem `stddev`, e o mesmo código precisa
rodar em PostgreSQL na produção.
"""

from collections import defaultdict
from statistics import mean, pstdev

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AlertaCompletude, RegistroVacinacao
from app.schemas import ResultadoVarredura

K_PADRAO = 2.0
MINIMO_MESES = 3


def _totais_mensais(db: Session) -> dict[str, dict[tuple[int, int], int]]:
    """{municipio_id: {(ano, mes): total_de_doses}} para os registros ativos.

    Agrupa pelo município de aplicação. Todos os `status_dado` entram: completude
    mede volume de coleta, não validade do dado.
    """
    ano = func.extract("year", RegistroVacinacao.data_vacinacao)
    mes = func.extract("month", RegistroVacinacao.data_vacinacao)
    linhas = (
        db.query(
            RegistroVacinacao.municipio_vacina_id.label("municipio_id"),
            ano.label("ano"),
            mes.label("mes"),
            func.sum(RegistroVacinacao.quantidade).label("total"),
        )
        .filter(RegistroVacinacao.ativo.is_(True))
        .group_by(RegistroVacinacao.municipio_vacina_id, ano, mes)
        .all()
    )

    series: dict[str, dict[tuple[int, int], int]] = defaultdict(dict)
    for linha in linhas:
        series[linha.municipio_id][(int(linha.ano), int(linha.mes))] = int(linha.total)
    return series


def _preencher_meses_ausentes(serie: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    """Completa com zero os meses sem nenhum registro dentro do intervalo coberto.

    Um mês que sumiu da base é justamente o caso que o RF15 precisa apontar; sem
    isso ele nem entraria na série e passaria despercebido.
    """
    chaves = sorted(serie)
    primeiro = chaves[0][0] * 12 + (chaves[0][1] - 1)
    ultimo = chaves[-1][0] * 12 + (chaves[-1][1] - 1)

    completa: dict[tuple[int, int], int] = {}
    for indice in range(primeiro, ultimo + 1):
        chave = (indice // 12, indice % 12 + 1)
        completa[chave] = serie.get(chave, 0)
    return completa


def _upsert_alerta(db: Session, ano: int, mes: int, municipio_id: str, total: int) -> bool:
    """Grava o alerta e devolve True se foi criado agora.

    Um alerta já existente tem apenas o total atualizado: o `status` definido pelo
    administrador (RF16) é preservado, senão cada varredura apagaria a triagem.
    """
    alerta = (
        db.query(AlertaCompletude)
        .filter(
            AlertaCompletude.referencia_ano == ano,
            AlertaCompletude.referencia_mes == mes,
            AlertaCompletude.municipio_id == municipio_id,
        )
        .first()
    )
    if alerta is not None:
        alerta.total_observado = total
        return False

    db.add(
        AlertaCompletude(
            referencia_ano=ano,
            referencia_mes=mes,
            municipio_id=municipio_id,
            total_observado=total,
            status="ABERTO",
        )
    )
    return True


def detectar_anomalias(
    db: Session, k: float = K_PADRAO, minimo_meses: int = MINIMO_MESES
) -> ResultadoVarredura:
    """Varre o histórico mensal de cada município e registra os meses anômalos."""
    criados = 0
    atualizados = 0
    municipios_analisados = 0
    meses_analisados = 0

    for municipio_id, serie in _totais_mensais(db).items():
        if len(serie) < minimo_meses:
            # Dois pontos não definem faixa nenhuma: alertar aqui só produziria
            # falso positivo para todo município pequeno ou recém-cadastrado.
            continue

        completa = _preencher_meses_ausentes(serie)
        municipios_analisados += 1
        meses_analisados += len(completa)

        totais = list(completa.values())
        limite_inferior = mean(totais) - k * pstdev(totais)

        for (ano, mes), total in completa.items():
            if total >= limite_inferior:
                continue
            if _upsert_alerta(db, ano, mes, municipio_id, total):
                criados += 1
            else:
                atualizados += 1

    db.commit()
    return ResultadoVarredura(
        alertas_criados=criados,
        alertas_atualizados=atualizados,
        municipios_analisados=municipios_analisados,
        meses_analisados=meses_analisados,
    )
