import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.dependencies import require_role, validate_municipio_scope
from app.main import app
from app.models import UsuarioAdmin
from app.security import get_password_hash, verify_password
from app.database import ensure_default_admin_user

client = TestClient(app)


def create_admin_user(db_session):
    user = UsuarioAdmin(
        email="admin@example.com",
        senha_hash=get_password_hash("senha123"),
        role="ADMIN"
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_default_admin_is_created_when_db_is_empty(monkeypatch, db_session):
    monkeypatch.setenv("DEFAULT_ADMIN_EMAIL", "root@imunizacao.local")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")

    ensure_default_admin_user()

    user = db_session.query(UsuarioAdmin).filter(UsuarioAdmin.email == "root@imunizacao.local").one()
    assert user.role == "ADMIN"
    assert verify_password("Admin@123", user.senha_hash) is True


def test_login_success(db_session):
    create_admin_user(db_session)
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "senha123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["role"] == "ADMIN"
    assert "access_token" in data


def test_login_accepts_local_domain_email(db_session):
    user = UsuarioAdmin(
        email="admin@imunizacao.local",
        senha_hash=get_password_hash("Admin@123"),
        role="ADMIN",
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/auth/login",
        json={"email": "admin@imunizacao.local", "password": "Admin@123"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


def test_login_wrong_password(db_session):
    create_admin_user(db_session)
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "senha_errada"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha incorretos."


def test_login_unknown_user():
    response = client.post(
        "/auth/login",
        json={"email": "naoexiste@example.com", "password": "senha123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha incorretos."


def test_protected_route_requires_valid_token(db_session):
    create_admin_user(db_session)
    response = client.get("/municipios")
    assert response.status_code == 401
    assert response.json()["detail"] == "Token ausente ou inválido."

    response = client.get("/municipios", headers={"Authorization": "Bearer token_invalido"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Token ausente ou inválido."


def test_protected_route_accepts_valid_token(db_session):
    create_admin_user(db_session)
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "senha123"},
    )
    token = login_response.json()["access_token"]

    response = client.get("/health", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_role_permission_checks():
    admin = UsuarioAdmin(email="admin@example.com", senha_hash="hash", role="ADMIN")
    municipal = UsuarioAdmin(
        email="municipal@example.com",
        senha_hash="hash",
        role="GESTOR_MUNICIPAL",
        municipio_alocado_id="2304400",
    )

    assert require_role(["ADMIN"])(current_user=admin) == admin

    with pytest.raises(HTTPException) as exc:
        require_role(["ADMIN"])(current_user=municipal)
    assert exc.value.status_code == 403


def test_municipal_scope_restricts_to_assigned_municipality():
    municipal = UsuarioAdmin(
        email="municipal@example.com",
        senha_hash="hash",
        role="GESTOR_MUNICIPAL",
        municipio_alocado_id="2304400",
    )
    estadual = UsuarioAdmin(
        email="estadual@example.com",
        senha_hash="hash",
        role="GESTOR_ESTADUAL",
    )
    admin = UsuarioAdmin(email="admin@example.com", senha_hash="hash", role="ADMIN")

    assert validate_municipio_scope(municipal, "2304400") == municipal

    with pytest.raises(HTTPException) as exc:
        validate_municipio_scope(municipal, "2300100")
    assert exc.value.status_code == 403

    assert validate_municipio_scope(estadual, "2300100") == estadual
    assert validate_municipio_scope(admin, "2300100") == admin
