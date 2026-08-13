import pytest
from app.models import RegistroVacinacao, UsuarioAdmin, AlertaCompletude, Municipio
from datetime import date
from sqlalchemy import text


def test_registro_vacinacao_chack_constraints():
    assert RegistroVacinacao.__table__.constraints
    check_names = {c.name for c in RegistroVacinacao.__table__.constraints if hasattr(c, 'name')}
    assert 'chk_quantidade_positiva' in check_names
    assert 'chk_status_dado' in check_names
    assert 'chk_idade_valida' in check_names


def test_usuario_admin_role_check():
    assert 'chk_user_role' in {c.name for c in UsuarioAdmin.__table__.constraints if hasattr(c, 'name')}


def test_alerta_completude_constraints():
    assert 'chk_mes_valido' in {c.name for c in AlertaCompletude.__table__.constraints if hasattr(c, 'name')}
    assert 'chk_alerta_status' in {c.name for c in AlertaCompletude.__table__.constraints if hasattr(c, 'name')}


def test_municipio_new_fields_exist():
    columns = {c.name for c in Municipio.__table__.columns}
    assert {"regiao_saude", "polo", "created_at", "updated_at"}.issubset(columns)
    assert Municipio.__table__.c.polo.nullable is False
    assert Municipio.__table__.c.regiao_saude.nullable is True
