"""Cobre a infraestrutura transversal: autenticação, RBAC, escopo por
município, tipos portáveis dos modelos e o middleware de token."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql, sqlite

from app.dependencies import (
    get_current_user,
    require_municipio_access,
    require_role,
    validate_municipio_scope,
)
from app.main import app
from app.models import GUID, JSONB, UsuarioAdmin
from app.security import create_access_token, get_password_hash, verify_password

client = TestClient(app)


def _usuario(db_session, email, role="ADMIN", municipio=None):
    user = UsuarioAdmin(
        email=email,
        senha_hash=get_password_hash("senha123"),
        role=role,
        municipio_alocado_id=municipio,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ============================================================
# SEGURANÇA / TOKEN
# ============================================================

def test_senha_e_verificada_pelo_hash():
    hash_ = get_password_hash("segredo")
    assert hash_ != "segredo"
    assert verify_password("segredo", hash_)
    assert not verify_password("errada", hash_)


def test_token_invalido_e_recusado_pelo_middleware():
    resposta = client.get("/auth/me", headers={"Authorization": "Bearer nao-e-um-jwt"})
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Token ausente ou inválido."


def test_token_sem_sub_e_recusado():
    token = create_access_token(data={"role": "ADMIN"})  # sem "sub"
    resposta = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 401


def test_cabecalho_sem_esquema_bearer_e_recusado():
    assert client.get("/auth/me", headers={"Authorization": "Token abc"}).status_code == 401


def test_rotas_publicas_dispensam_token():
    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_me_devolve_o_usuario_do_token(db_session):
    _usuario(db_session, "me@example.com", role="GESTOR_MUNICIPAL", municipio="2304400")
    token = client.post(
        "/auth/login", json={"email": "me@example.com", "password": "senha123"}
    ).json()["access_token"]

    corpo = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    assert corpo["email"] == "me@example.com"
    assert corpo["role"] == "GESTOR_MUNICIPAL"
    assert corpo["municipio_alocado_id"] == "2304400"


def test_login_com_email_inexistente(db_session):
    resposta = client.post(
        "/auth/login", json={"email": "ninguem@example.com", "password": "x"}
    )
    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "E-mail ou senha incorretos."


def test_login_com_senha_errada(db_session):
    _usuario(db_session, "senha@example.com")
    resposta = client.post(
        "/auth/login", json={"email": "senha@example.com", "password": "errada"}
    )
    assert resposta.status_code == 401


def test_login_normaliza_o_email(db_session):
    _usuario(db_session, "caixa@example.com")
    resposta = client.post(
        "/auth/login", json={"email": "  CAIXA@Example.com  ", "password": "senha123"}
    )
    assert resposta.status_code == 200


def test_login_com_email_vazio_e_rejeitado():
    assert client.post("/auth/login", json={"email": "   ", "password": "x"}).status_code == 422


def test_usuario_do_token_precisa_existir_no_banco(db_session):
    """Token bem formado, mas de um usuário que não está mais cadastrado."""
    token = create_access_token(data={"sub": "fantasma@example.com", "role": "ADMIN"})
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_get_current_user_rejeita_token_malformado(db_session):
    with pytest.raises(HTTPException) as exc:
        get_current_user(token="lixo", db=db_session)
    assert exc.value.status_code == 401


# ============================================================
# RBAC E ESCOPO POR MUNICÍPIO
# ============================================================

def test_require_role_libera_perfil_permitido(db_session):
    admin = _usuario(db_session, "rbac-ok@example.com", role="ADMIN")
    assert require_role(["ADMIN"])(current_user=admin) is admin


def test_require_role_bloqueia_perfil_nao_permitido(db_session):
    gestor = _usuario(db_session, "rbac-nao@example.com", role="GESTOR_MUNICIPAL")
    with pytest.raises(HTTPException) as exc:
        require_role(["ADMIN"])(current_user=gestor)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["ADMIN", "GESTOR_ESTADUAL"])
def test_perfis_amplos_acessam_qualquer_municipio(db_session, role):
    user = _usuario(db_session, f"amplo-{role}@example.com", role=role)
    assert validate_municipio_scope(user, "9999999") is user


def test_gestor_municipal_acessa_o_proprio_municipio(db_session):
    user = _usuario(db_session, "escopo-ok@example.com", role="GESTOR_MUNICIPAL",
                    municipio="2304400")
    assert validate_municipio_scope(user, "2304400") is user


def test_gestor_municipal_nao_acessa_outro_municipio(db_session):
    user = _usuario(db_session, "escopo-nao@example.com", role="GESTOR_MUNICIPAL",
                    municipio="2304400")
    with pytest.raises(HTTPException) as exc:
        validate_municipio_scope(user, "2303709")
    assert exc.value.status_code == 403


def test_gestor_municipal_sem_municipio_vinculado(db_session):
    user = _usuario(db_session, "sem-municipio@example.com", role="GESTOR_MUNICIPAL")
    with pytest.raises(HTTPException) as exc:
        validate_municipio_scope(user, "2304400")
    assert exc.value.status_code == 403
    assert "sem município vinculado" in exc.value.detail


def test_perfil_desconhecido_e_bloqueado(db_session):
    user = _usuario(db_session, "perfil-estranho@example.com", role="ADMIN")
    user.role = "VISITANTE"  # não passa pelo CHECK do banco, mas cobre a guarda
    with pytest.raises(HTTPException) as exc:
        validate_municipio_scope(user, "2304400")
    assert exc.value.status_code == 403


def test_require_municipio_access_monta_a_dependencia(db_session):
    user = _usuario(db_session, "dep@example.com", role="GESTOR_MUNICIPAL",
                    municipio="2304400")
    checker = require_municipio_access("2304400")
    assert checker(current_user=user) is user


# ============================================================
# TIPOS PORTÁVEIS DOS MODELOS
# ============================================================

def test_guid_usa_uuid_nativo_no_postgres_e_char_no_sqlite():
    tipo = GUID()
    assert "UUID" in type(tipo.load_dialect_impl(postgresql.dialect())).__name__.upper()
    assert "CHAR" in type(tipo.load_dialect_impl(sqlite.dialect())).__name__.upper()


def test_guid_converte_valores_de_ida():
    tipo = GUID()
    valor = uuid.uuid4()

    assert tipo.process_bind_param(None, sqlite.dialect()) is None
    assert tipo.process_bind_param(valor, postgresql.dialect()) is valor
    assert tipo.process_bind_param(valor, sqlite.dialect()) == str(valor)
    assert tipo.process_bind_param(str(valor), sqlite.dialect()) == str(valor)


def test_guid_converte_valores_de_volta():
    tipo = GUID()
    valor = uuid.uuid4()

    assert tipo.process_result_value(None, sqlite.dialect()) is None
    assert tipo.process_result_value(str(valor), sqlite.dialect()) == valor
    assert tipo.process_result_value(valor, sqlite.dialect()) == valor


def test_jsonb_usa_tipo_nativo_no_postgres():
    tipo = JSONB()
    assert "JSONB" in type(tipo.load_dialect_impl(postgresql.dialect())).__name__.upper()
    assert tipo.load_dialect_impl(sqlite.dialect()) is not None
