import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models import UsuarioAdmin
from app.security import get_password_hash

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    user = UsuarioAdmin(
        email="admin@example.com",
        senha_hash=get_password_hash("senha123"),
        role="ADMIN"
    )
    db.add(user)
    db.commit()
    db.close()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_login_success():
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "senha123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["role"] == "ADMIN"
    assert "access_token" in data


def test_login_wrong_password():
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
