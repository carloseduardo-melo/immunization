from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, UsuarioAdmin
from app.security import get_password_hash

client = TestClient(app)


def create_user(db_session, email, role):
    user = UsuarioAdmin(
        email=email,
        senha_hash=get_password_hash("senha123"),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(email):
    response = client.post("/auth/login", json={"email": email, "password": "senha123"})
    return response.json()["access_token"]


def auth_headers(db_session, role, email="user@example.com"):
    create_user(db_session, email, role)
    token = login(email)
    return {"Authorization": f"Bearer {token}"}


def create_municipio(db_session, id_ibge="2304400", nome="Fortaleza", uf="CE",
                      regiao_saude="Região de Fortaleza", polo=True, ativo=True):
    municipio = Municipio(
        id_ibge=id_ibge, nome=nome, uf=uf,
        regiao_saude=regiao_saude, polo=polo, ativo=ativo,
    )
    db_session.add(municipio)
    db_session.commit()
    return municipio


def test_listar_municipios_padrao(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_municipio(db_session, id_ibge="2304400", nome="Fortaleza")
    create_municipio(db_session, id_ibge="2312908", nome="Sobral", polo=False)

    response = client.get("/municipios", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] == 1
    assert {item["nome"] for item in data["items"]} == {"Fortaleza", "Sobral"}


def test_listar_municipios_filtro_uf(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_municipio(db_session, id_ibge="2304400", nome="Fortaleza", uf="CE")
    create_municipio(db_session, id_ibge="2611606", nome="Recife", uf="PE")

    response = client.get("/municipios?uf=CE", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Fortaleza"


def test_listar_municipios_filtro_ativo_true(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_municipio(db_session, id_ibge="2304400", nome="Fortaleza", ativo=True)
    create_municipio(db_session, id_ibge="2312908", nome="Sobral", ativo=False)

    response = client.get("/municipios?ativo=true", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Fortaleza"


def test_listar_municipios_filtro_ativo_false(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_municipio(db_session, id_ibge="2304400", nome="Fortaleza", ativo=True)
    create_municipio(db_session, id_ibge="2312908", nome="Sobral", ativo=False)

    response = client.get("/municipios?ativo=false", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Sobral"


def test_listar_municipios_busca_por_nome(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_municipio(db_session, id_ibge="2304400", nome="Fortaleza")
    create_municipio(db_session, id_ibge="2312908", nome="Sobral")

    response = client.get("/municipios?search=fort", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Fortaleza"


def test_listar_municipios_paginacao(db_session):
    headers = auth_headers(db_session, "ADMIN")
    for i in range(15):
        create_municipio(db_session, id_ibge=f"23{i:05d}", nome=f"Municipio {i:02d}")

    response = client.get("/municipios?page=2&page_size=10", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert data["page"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 5


def test_listar_municipios_lista_vazia(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.get("/municipios", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["total_pages"] == 0
