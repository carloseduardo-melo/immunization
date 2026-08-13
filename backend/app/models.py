import uuid

from sqlalchemy import (
    Column, String, Boolean, Integer, SmallInteger, Date, DateTime,
    ForeignKey, CheckConstraint, Index, text, TIMESTAMP, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB as PG_JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class JSONB(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


Base = declarative_base()

class Municipio(Base):
    __tablename__ = "municipios"

    id_ibge = Column(String(7), primary_key=True)
    nome = Column(String(150), nullable=False)
    uf = Column(String(2), nullable=False)
    regiao_saude = Column(String(150), nullable=True)
    polo = Column(Boolean, nullable=False, server_default=text("false"))
    ativo = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), default=func.now(), onupdate=func.now())

    # Relacionamentos
    alertas = relationship("AlertaCompletude", back_populates="municipio")


class Vacina(Base):
    __tablename__ = "vacinas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(150), unique=True, nullable=False)
    alta_complexidade = Column(Boolean, nullable=False, server_default=text("false"))
    ativo = Column(Boolean, nullable=False, server_default=text("true"))


class RegistroVacinacao(Base):
    __tablename__ = "registros_vacinacao"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    data_vacinacao = Column(Date, nullable=False)
    idade = Column(SmallInteger, nullable=True) # Aceita NULL
    vacina_id = Column(Integer, ForeignKey("vacinas.id"), nullable=True) # Aceita NULL
    municipio_residencia_id = Column(String(7), ForeignKey("municipios.id_ibge"), nullable=True) # Aceita NULL
    municipio_vacina_id = Column(String(7), ForeignKey("municipios.id_ibge"), nullable=False)
    teve_deslocamento = Column(Boolean, nullable=True)
    quantidade = Column(Integer, nullable=False, server_default=text("1"))
    status_dado = Column(String(30), nullable=False, server_default=text("'VALIDO'"))

    __table_args__ = (
        CheckConstraint("quantidade > 0", name="chk_quantidade_positiva"),
        CheckConstraint(
            "status_dado IN ('VALIDO', 'DADO_INCONSISTENTE', 'DESLOCAMENTO_INDETERMINADO')", 
            name="chk_status_dado"
        ),
        CheckConstraint(
            "(idade IS NULL) OR (idade >= 0 AND idade <= 110) OR (status_dado = 'DADO_INCONSISTENTE')",
            name="chk_idade_valida"
        ),
        Index("idx_registro_data", "data_vacinacao"),
        Index("idx_registro_local", "municipio_vacina_id"),
        Index("idx_registro_vacina", "vacina_id"),
        Index("idx_registro_residencia", "municipio_residencia_id"),
    )


class UsuarioAdmin(Base):
    __tablename__ = "usuarios_admin"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(150), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, server_default=text("'GESTOR_MUNICIPAL'"))
    municipio_alocado_id = Column(String(7), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "role IN ('GESTOR_ESTADUAL', 'GESTOR_MUNICIPAL', 'ADMIN')", 
            name="chk_user_role"
        ),
    )


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tabela = Column(String(50), nullable=False)
    registro_id = Column(GUID(), nullable=False)
    acao = Column(String(10), nullable=False)
    usuario_id = Column(GUID(), ForeignKey("usuarios_admin.id"), nullable=False)
    valores_antigos = Column(JSONB, nullable=True)
    valores_novos = Column(JSONB, nullable=True)
    criado_em = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("acao IN ('UPDATE', 'DELETE')", name="chk_log_acao"),
        Index("idx_auditoria_registro", "tabela", "registro_id"),
    )


class AlertaCompletude(Base):
    __tablename__ = "alertas_completude"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    referencia_ano = Column(SmallInteger, nullable=False)
    referencia_mes = Column(SmallInteger, nullable=False)
    municipio_id = Column(String(7), ForeignKey("municipios.id_ibge"), nullable=True)
    total_observado = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, server_default=text("'ABERTO'"))
    criado_em = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    municipio = relationship("Municipio", back_populates="alertas")

    __table_args__ = (
        CheckConstraint("referencia_mes BETWEEN 1 AND 12", name="chk_mes_valido"),
        CheckConstraint(
            "status IN ('ABERTO', 'INVESTIGANDO', 'RESOLVIDO', 'FALSO_POSITIVO')", 
            name="chk_alerta_status"
        ),
    )