from fastapi.testclient import TestClient

from app.main import app
from app.models import UsuarioAdmin, Vacina
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


def create_vacina(db_session, nome="BCG", alta_complexidade=False, ativo=True):
    vacina = Vacina(nome=nome, alta_complexidade=alta_complexidade, ativo=ativo)
    db_session.add(vacina)
    db_session.commit()
    db_session.refresh(vacina)
    return vacina


# --- LISTAGEM ---


def test_listar_vacinas_padrao(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG")
    create_vacina(db_session, nome="Febre Amarela")

    response = client.get("/vacinas", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert {item["nome"] for item in data["items"]} == {"BCG", "Febre Amarela"}


def test_listar_vacinas_filtro_alta_complexidade(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG", alta_complexidade=False)
    create_vacina(db_session, nome="Imunoglobulina", alta_complexidade=True)

    response = client.get("/vacinas?alta_complexidade=true", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Imunoglobulina"


def test_listar_vacinas_filtro_ativo_false(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG", ativo=True)
    create_vacina(db_session, nome="Sarampo", ativo=False)

    response = client.get("/vacinas?ativo=false", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Sarampo"


def test_listar_vacinas_busca_por_nome(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG")
    create_vacina(db_session, nome="Febre Amarela")

    response = client.get("/vacinas?search=febre", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["nome"] == "Febre Amarela"


def test_listar_vacinas_paginacao(db_session):
    headers = auth_headers(db_session, "ADMIN")
    for i in range(15):
        create_vacina(db_session, nome=f"Vacina {i:02d}")

    response = client.get("/vacinas?page=2&page_size=10", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert data["page"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 5


def test_listar_vacinas_lista_vazia(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.get("/vacinas", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["total_pages"] == 0


def test_listar_vacinas_sem_token(db_session):
    response = client.get("/vacinas")

    assert response.status_code == 401


# --- CRIAÇÃO ---


def test_criar_vacina_sucesso(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.post(
        "/vacinas",
        json={"nome": "BCG", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["nome"] == "BCG"
    assert data["ativo"] is True
    assert data["alta_complexidade"] is False


def test_criar_vacina_campos_obrigatorios(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.post(
        "/vacinas",
        json={"nome": "", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 422


def test_criar_vacina_nome_duplicado_case_insensitive(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG")

    response = client.post(
        "/vacinas",
        json={"nome": "bcg", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 409


def test_criar_vacina_sem_permissao(db_session):
    headers = auth_headers(db_session, "GESTOR_MUNICIPAL")

    response = client.post(
        "/vacinas",
        json={"nome": "BCG", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 403


def test_criar_vacina_alta_complexidade_admin_permitido(db_session):
    # Regressão: current_user.perfil (inexistente) quebrava com 500 nesse caminho.
    headers = auth_headers(db_session, "ADMIN")

    response = client.post(
        "/vacinas",
        json={"nome": "Imunoglobulina", "alta_complexidade": True},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["alta_complexidade"] is True


def test_criar_vacina_alta_complexidade_gestor_estadual_bloqueado(db_session):
    # Regressão: current_user.perfil (inexistente) quebrava com 500 nesse caminho.
    headers = auth_headers(db_session, "GESTOR_ESTADUAL")

    response = client.post(
        "/vacinas",
        json={"nome": "Imunoglobulina", "alta_complexidade": True},
        headers=headers,
    )

    assert response.status_code == 403


# --- ATUALIZAÇÃO ---


def test_atualizar_vacina_sucesso(db_session):
    headers = auth_headers(db_session, "GESTOR_ESTADUAL")
    vacina = create_vacina(db_session, nome="BCG")

    response = client.put(
        f"/vacinas/{vacina.id}",
        json={"nome": "BCG Atualizada", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "BCG Atualizada"


def test_atualizar_vacina_nao_encontrada(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.put(
        "/vacinas/9999",
        json={"nome": "Inexistente", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 404


def test_atualizar_vacina_nome_duplicado(db_session):
    headers = auth_headers(db_session, "ADMIN")
    create_vacina(db_session, nome="BCG")
    outra = create_vacina(db_session, nome="Febre Amarela")

    response = client.put(
        f"/vacinas/{outra.id}",
        json={"nome": "bcg", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 409


def test_atualizar_vacina_sem_permissao(db_session):
    headers = auth_headers(db_session, "GESTOR_MUNICIPAL")
    vacina = create_vacina(db_session, nome="BCG")

    response = client.put(
        f"/vacinas/{vacina.id}",
        json={"nome": "Nova", "alta_complexidade": False},
        headers=headers,
    )

    assert response.status_code == 403


def test_atualizar_vacina_mudar_complexidade_admin_permitido(db_session):
    # Regressão: current_user.perfil (inexistente) quebrava com 500 nesse caminho.
    headers = auth_headers(db_session, "ADMIN")
    vacina = create_vacina(db_session, nome="BCG", alta_complexidade=False)

    response = client.put(
        f"/vacinas/{vacina.id}",
        json={"nome": "BCG", "alta_complexidade": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["alta_complexidade"] is True


def test_atualizar_vacina_mudar_complexidade_gestor_estadual_bloqueado(db_session):
    # Regressão: current_user.perfil (inexistente) quebrava com 500 nesse caminho.
    headers = auth_headers(db_session, "GESTOR_ESTADUAL")
    vacina = create_vacina(db_session, nome="BCG", alta_complexidade=False)

    response = client.put(
        f"/vacinas/{vacina.id}",
        json={"nome": "BCG", "alta_complexidade": True},
        headers=headers,
    )

    assert response.status_code == 403


def test_atualizar_vacina_sem_mudar_complexidade_gestor_estadual_permitido(db_session):
    headers = auth_headers(db_session, "GESTOR_ESTADUAL")
    vacina = create_vacina(db_session, nome="BCG", alta_complexidade=True)

    response = client.put(
        f"/vacinas/{vacina.id}",
        json={"nome": "BCG Renomeada", "alta_complexidade": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "BCG Renomeada"


# --- DESATIVAÇÃO ---


def test_desativar_vacina_soft_delete(db_session):
    headers = auth_headers(db_session, "ADMIN")
    vacina = create_vacina(db_session, nome="BCG", ativo=True)

    response = client.delete(f"/vacinas/{vacina.id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["ativo"] is False

    db_vacina = db_session.query(Vacina).filter(Vacina.id == vacina.id).first()
    assert db_vacina is not None
    assert db_vacina.ativo is False


def test_desativar_vacina_nao_encontrada(db_session):
    headers = auth_headers(db_session, "ADMIN")

    response = client.delete("/vacinas/9999", headers=headers)

    assert response.status_code == 404


def test_desativar_vacina_sem_permissao(db_session):
    headers = auth_headers(db_session, "GESTOR_MUNICIPAL")
    vacina = create_vacina(db_session, nome="BCG")

    response = client.delete(f"/vacinas/{vacina.id}", headers=headers)

    assert response.status_code == 403
