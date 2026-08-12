from fastapi.testclient import TestClient
from app.main import app
from app.models import UsuarioAdmin
from app.security import get_password_hash

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
