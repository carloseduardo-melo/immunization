"""RF21, RF22 e RNF09 - camada de serviço do log de auditoria.

Toda gravação em `log_auditoria` passa por aqui: os routers só informam o que
mudou, nunca montam a linha de log. Isso é o que garante o critério do RF21 de
que o registro não depende do frontend enviar nada — e mantém o formato do
snapshot igual para as três tabelas auditadas.

A leitura (RF22) também mora aqui, na forma de uma query montada com os filtros,
para que o router fique só com paginação e serialização.

Nenhuma função deste módulo altera ou apaga uma linha existente. O expurgo é a
única remoção prevista e é deliberadamente uma rotina de manutenção, chamada
pelo script `scripts/expurgar_auditoria.py`, fora do alcance da API (RNF09).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import LogAuditoria, UsuarioAdmin

# Retenção mínima do log, alinhada à janela de backup do banco (RNF09).
# O expurgo recusa qualquer janela menor que esta.
RETENCAO_DIAS_MINIMA = 30

# Tabelas de dado de negócio cobertas pelo RF21. Alimenta o filtro da tela.
TABELAS_AUDITADAS = ("registros_vacinacao", "municipios", "vacinas")

ACOES = ("UPDATE", "DELETE")


def _valor_json(valor: Any) -> Any:
    """Converte um valor de coluna para algo que JSON/JSONB aceite."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, (UUID, Decimal)):
        return str(valor)
    return valor


def serializar(obj) -> dict:
    """Snapshot JSON-safe de todas as colunas de uma instância do ORM.

    Genérico de propósito: municípios, vacinas e registros de vacinação têm
    colunas diferentes, e o log precisa guardar a linha inteira de cada um sem
    que o serviço conheça o formato de nenhum deles.
    """
    return {
        coluna.name: _valor_json(getattr(obj, coluna.name))
        for coluna in obj.__table__.columns
    }


def registrar(
    db: Session,
    *,
    tabela: str,
    registro_id: Any,
    acao: str,
    usuario: UsuarioAdmin,
    valores_antigos: Optional[dict],
    valores_novos: Optional[dict],
) -> LogAuditoria:
    """RF21 - enfileira a linha de auditoria na sessão, sem commit.

    Quem chama controla a transação: o log precisa ser gravado no mesmo commit
    da alteração que ele descreve, senão um erro no meio do caminho deixaria um
    dos dois sem o outro.
    """
    log = LogAuditoria(
        tabela=tabela,
        registro_id=str(registro_id),
        acao=acao,
        usuario_id=usuario.id,
        valores_antigos=valores_antigos,
        valores_novos=valores_novos,
    )
    db.add(log)
    return log


def construir_query_logs(
    db: Session,
    usuario_id: Optional[UUID] = None,
    tabela: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
):
    """RF22 - query de (log, e-mail do autor) já filtrada e ordenada.

    O join com `usuarios_admin` é interno: `usuario_id` é NOT NULL com chave
    estrangeira, então todo log tem autor. `data_fim` é inclusiva — o usuário
    escolhe um dia no calendário, não um instante, e um log das 23h daquele dia
    precisa entrar no recorte.
    """
    query = db.query(LogAuditoria, UsuarioAdmin.email.label("usuario_email")).join(
        UsuarioAdmin, LogAuditoria.usuario_id == UsuarioAdmin.id
    )

    if usuario_id is not None:
        query = query.filter(LogAuditoria.usuario_id == usuario_id)

    if tabela:
        query = query.filter(LogAuditoria.tabela == tabela)

    if data_inicio is not None:
        query = query.filter(LogAuditoria.criado_em >= datetime.combine(data_inicio, datetime.min.time()))

    if data_fim is not None:
        limite = datetime.combine(data_fim, datetime.min.time()) + timedelta(days=1)
        query = query.filter(LogAuditoria.criado_em < limite)

    return query.order_by(LogAuditoria.criado_em.desc(), LogAuditoria.id)


def listar_usuarios_com_log(db: Session) -> list[UsuarioAdmin]:
    """RF22 - autores que aparecem no log, para o seletor da tela.

    Listar todos os usuários cadastrados encheria o seletor de gente que nunca
    alterou nada; o filtro só é útil sobre quem tem log.
    """
    return (
        db.query(UsuarioAdmin)
        .join(LogAuditoria, LogAuditoria.usuario_id == UsuarioAdmin.id)
        .distinct()
        .order_by(UsuarioAdmin.email)
        .all()
    )


def expurgar_logs_antigos(db: Session, dias: int) -> int:
    """RNF09 - remove logs mais antigos que `dias` e devolve quantos saíram.

    Rotina de manutenção, chamada por `scripts/expurgar_auditoria.py`. Não é
    exposta em nenhum endpoint, e recusa qualquer janela abaixo da retenção
    mínima para que um erro de digitação não apague o log recente.
    """
    if dias < RETENCAO_DIAS_MINIMA:
        raise ValueError(
            f"A retenção mínima do log de auditoria é de {RETENCAO_DIAS_MINIMA} dias; "
            f"recebido: {dias}."
        )

    corte = datetime.utcnow() - timedelta(days=dias)
    removidos = (
        db.query(LogAuditoria)
        .filter(LogAuditoria.criado_em < corte)
        .delete(synchronize_session=False)
    )
    db.commit()
    return removidos
