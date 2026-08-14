from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash

client = TestClient(app)


def create_user(db_session, email, role, municipio_id=None):
    user = UsuarioAdmin(
        email=email,
        senha_hash=get_password_hash("senha123"),
        role=role,
        municipio_alocado_id=municipio_id,
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(email):
    response = client.post("/auth/login", json={"email": email, "password": "senha123"})
    return response.json()["access_token"]


def auth_headers(db_session, role="ADMIN", email="user@example.com", municipio_id=None):
    create_user(db_session, email, role, municipio_id=municipio_id)
    token = login(email)
    return {"Authorization": f"Bearer {token}"}


def setup_dados_base(db_session):
    mun1 = Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE")
    mun2 = Municipio(id_ibge="2303709", nome="Caucaia", uf="CE")
    db_session.add_all([mun1, mun2])

    vac1 = Vacina(nome="COVID-19", alta_complexidade=False)
    vac2 = Vacina(nome="Influenza", alta_complexidade=False)
    db_session.add_all([vac1, vac2])

    db_session.commit()
    db_session.refresh(vac1)
    db_session.refresh(vac2)

    reg1 = RegistroVacinacao(
        data_vacinacao=date(2024, 1, 15),
        idade=25,
        vacina_id=vac1.id,
        municipio_residencia_id="2304400",
        municipio_vacina_id="2304400",
        teve_deslocamento=False,
        quantidade=1,
        status_dado="VALIDO",
    )
    reg2 = RegistroVacinacao(
        data_vacinacao=date(2024, 2, 10),
        idade=65,
        vacina_id=vac2.id,
        municipio_residencia_id="2303709",
        municipio_vacina_id="2304400",
        teve_deslocamento=True,
        quantidade=2,
        status_dado="VALIDO",
    )
    reg3 = RegistroVacinacao(
        data_vacinacao=date(2024, 3, 5),
        idade=120,
        vacina_id=vac1.id,
        municipio_residencia_id="2304400",
        municipio_vacina_id="2304400",
        teve_deslocamento=False,
        quantidade=1,
        status_dado="DADO_INCONSISTENTE",
    )
    db_session.add_all([reg1, reg2, reg3])
    db_session.commit()

    return mun1, mun2, vac1, vac2


def test_listar_registros_sem_token():
    response = client.get("/registros")
    assert response.status_code == 401


def test_listar_registros_vazio(db_session):
    headers = auth_headers(db_session, "ADMIN")
    response = client.get("/registros", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_listar_registros_com_dados(db_session):
    headers = auth_headers(db_session, "ADMIN")
    setup_dados_base(db_session)

    response = client.get("/registros", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 10


def test_listar_registros_filtro_municipio(db_session):
    headers = auth_headers(db_session, "ADMIN")
    setup_dados_base(db_session)

    # Filtra por município de residência Caucaia (2303709)
    response = client.get("/registros?municipio_id=2303709", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["municipio_residencia_id"] == "2303709"


def test_listar_registros_filtro_vacina(db_session):
    headers = auth_headers(db_session, "ADMIN")
    _, _, _, vac2 = setup_dados_base(db_session)

    response = client.get(f"/registros?vacina_id={vac2.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["vacina_nome"] == "Influenza"


def test_listar_registros_filtro_datas(db_session):
    headers = auth_headers(db_session, "ADMIN")
    setup_dados_base(db_session)

    response = client.get("/registros?data_inicio=2024-02-01&data_fim=2024-02-28", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["data_vacinacao"] == "2024-02-10"


def test_listar_registros_filtro_idade(db_session):
    headers = auth_headers(db_session, "ADMIN")
    setup_dados_base(db_session)

    response = client.get("/registros?idade_min=60&idade_max=70", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["idade"] == 65


def test_listar_registros_filtro_status(db_session):
    headers = auth_headers(db_session, "ADMIN")
    setup_dados_base(db_session)

    response = client.get("/registros?status_dado=DADO_INCONSISTENTE", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status_dado"] == "DADO_INCONSISTENTE"


# --- CADASTRO MANUAL (RF07) ---


def test_criar_registro_sucesso(db_session):
    headers = auth_headers(db_session, "ADMIN")
    mun1, mun2, vac1, _ = setup_dados_base(db_session)

    payload = {
        "data_vacinacao": "2024-05-20",
        "municipio_vacina_id": mun1.id_ibge,
        "municipio_residencia_id": mun2.id_ibge,
        "vacina_id": vac1.id,
        "idade": 30,
        "quantidade": 1,
    }

    response = client.post("/registros", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status_dado"] == "VALIDO"
    assert data["teve_deslocamento"] is True
    assert data["municipio_vacina_nome"] == "Fortaleza"
    assert data["municipio_residencia_nome"] == "Caucaia"
    assert data["vacina_nome"] == "COVID-19"


def test_criar_registro_sem_residencia(db_session):
    headers = auth_headers(db_session, "ADMIN")
    mun1, _, vac1, _ = setup_dados_base(db_session)

    payload = {
        "data_vacinacao": "2024-05-20",
        "municipio_vacina_id": mun1.id_ibge,
        "municipio_residencia_id": None,
        "vacina_id": vac1.id,
        "idade": 25,
    }

    response = client.post("/registros", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status_dado"] == "DESLOCAMENTO_INDETERMINADO"
    assert data["teve_deslocamento"] is None


def test_criar_registro_idade_inconsistente(db_session):
    headers = auth_headers(db_session, "ADMIN")
    mun1, mun2, vac1, _ = setup_dados_base(db_session)

    payload = {
        "data_vacinacao": "2024-05-20",
        "municipio_vacina_id": mun1.id_ibge,
        "municipio_residencia_id": mun2.id_ibge,
        "vacina_id": vac1.id,
        "idade": 150,  # Idade fora de 0-110 anos
    }

    response = client.post("/registros", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status_dado"] == "DADO_INCONSISTENTE"
    assert data["teve_deslocamento"] is True


def test_criar_registro_municipio_inexistente(db_session):
    headers = auth_headers(db_session, "ADMIN")
    _, _, vac1, _ = setup_dados_base(db_session)

    payload = {
        "data_vacinacao": "2024-05-20",
        "municipio_vacina_id": "9999999",  # Código IBGE inexistente
        "vacina_id": vac1.id,
    }

    response = client.post("/registros", json=payload, headers=headers)
    assert response.status_code == 404
    assert "Município de aplicação não encontrado" in response.json()["detail"]

