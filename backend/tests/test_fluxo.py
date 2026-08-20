from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash
from app.sql_views import marcar_fluxo_desatualizado

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


def auth_headers(db_session, role="ADMIN", email="user@example.com"):
    create_user(db_session, email, role)
    token = login(email)
    return {"Authorization": f"Bearer {token}"}


def setup_fluxo_dados(db_session):
    """Cria um cenário com 3 municípios e movimentação real entre eles:

    - Fortaleza (polo): recebe de Caucaia e de Maracanaú -> saldo positivo.
    - Caucaia: só perde pacientes para Fortaleza -> saldo negativo (evasão).
    - Maracanaú: perde para Fortaleza, mas também aplica em residentes
      próprios (não entra no fluxo, pois não houve deslocamento).
    """
    fortaleza = Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE")
    caucaia = Municipio(id_ibge="2303709", nome="Caucaia", uf="CE")
    maracanau = Municipio(id_ibge="2308009", nome="Maracanaú", uf="CE")
    db_session.add_all([fortaleza, caucaia, maracanau])

    covid = Vacina(nome="COVID-19", alta_complexidade=False)
    flu = Vacina(nome="Influenza", alta_complexidade=False)
    db_session.add_all([covid, flu])
    db_session.commit()
    db_session.refresh(covid)
    db_session.refresh(flu)

    registros = [
        # Caucaia -> Fortaleza (COVID), 2024-01-10, quantidade 3
        RegistroVacinacao(
            data_vacinacao=date(2024, 1, 10),
            vacina_id=covid.id,
            municipio_residencia_id="2303709",
            municipio_vacina_id="2304400",
            teve_deslocamento=True,
            quantidade=3,
            status_dado="VALIDO",
        ),
        # Maracanaú -> Fortaleza (Influenza), 2024, 02, 05, quantidade 5
        RegistroVacinacao(
            data_vacinacao=date(2024, 2, 5),
            vacina_id=flu.id,
            municipio_residencia_id="2308009",
            municipio_vacina_id="2304400",
            teve_deslocamento=True,
            quantidade=5,
            status_dado="VALIDO",
        ),
        # Residente de Maracanaú vacinado em Maracanaú: sem deslocamento, não entra no fluxo
        RegistroVacinacao(
            data_vacinacao=date(2024, 2, 6),
            vacina_id=flu.id,
            municipio_residencia_id="2308009",
            municipio_vacina_id="2308009",
            teve_deslocamento=False,
            quantidade=10,
            status_dado="VALIDO",
        ),
        # Registro inconsistente com deslocamento: não deve entrar no fluxo (status != VALIDO)
        RegistroVacinacao(
            data_vacinacao=date(2024, 1, 15),
            vacina_id=covid.id,
            municipio_residencia_id="2303709",
            municipio_vacina_id="2304400",
            teve_deslocamento=True,
            quantidade=99,
            status_dado="DADO_INCONSISTENTE",
        ),
    ]
    db_session.add_all(registros)
    db_session.commit()

    # No PostgreSQL a view é MATERIALIZADA, ou seja, um retrato dos dados no
    # momento da última agregação — inserir registros não a atualiza sozinha.
    # Em produção quem marca a view são as escritas em /registros; aqui os
    # dados entram direto pelo ORM, então a marca é posta à mão para que a
    # primeira leitura de /fluxo reagregue (mesmo caminho da aplicação real).
    marcar_fluxo_desatualizado(db_session)
    db_session.commit()

    return {"fortaleza": fortaleza, "caucaia": caucaia, "maracanau": maracanau, "covid": covid, "flu": flu}


def test_fluxo_intermunicipal_agrega_origem_destino(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    response = client.get("/fluxo/intermunicipal", headers=headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2

    pares = {(item["municipio_origem_id"], item["municipio_destino_id"]): item["total_doses"] for item in items}
    assert pares[("2303709", "2304400")] == 3
    assert pares[("2308009", "2304400")] == 5
    # Sem deslocamento não aparece
    assert ("2308009", "2308009") not in pares


def test_fluxo_intermunicipal_filtra_por_vacina(db_session):
    dados = setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    response = client.get(
        "/fluxo/intermunicipal", headers=headers, params={"vacina_id": dados["covid"].id}
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["municipio_origem_id"] == "2303709"
    assert items[0]["total_doses"] == 3


def test_fluxo_intermunicipal_filtra_por_periodo(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    response = client.get(
        "/fluxo/intermunicipal",
        headers=headers,
        params={"data_inicio": "2024-02-01", "data_fim": "2024-02-28"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["municipio_origem_id"] == "2308009"
    assert items[0]["total_doses"] == 5


def test_fluxo_intermunicipal_requer_autenticacao():
    response = client.get("/fluxo/intermunicipal")
    assert response.status_code == 401


def test_fluxo_ranking_calcula_saldo_liquido(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    response = client.get("/fluxo/ranking", headers=headers)

    assert response.status_code == 200
    data = response.json()

    fortaleza = next(item for item in data["top_polo"] if item["municipio_id"] == "2304400")
    assert fortaleza["total_recebido"] == 8
    assert fortaleza["total_perdido"] == 0
    assert fortaleza["saldo_liquido"] == 8

    caucaia = next(item for item in data["top_evasao"] if item["municipio_id"] == "2303709")
    assert caucaia["total_perdido"] == 3
    assert caucaia["saldo_liquido"] == -3

    # Fortaleza deve ser o primeiro do ranking de polos (maior saldo)
    assert data["top_polo"][0]["municipio_id"] == "2304400"
    # Caucaia ou Maracanaú devem liderar o ranking de evasão (saldo mais negativo)
    assert data["top_evasao"][0]["saldo_liquido"] < 0


def test_fluxo_ranking_respeita_limit(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    response = client.get("/fluxo/ranking", headers=headers, params={"limit": 1})

    assert response.status_code == 200
    data = response.json()
    assert len(data["top_polo"]) == 1
    assert len(data["top_evasao"]) == 1


def test_fluxo_ranking_requer_autenticacao():
    response = client.get("/fluxo/ranking")
    assert response.status_code == 401


def test_escrita_marca_view_e_leitura_limpa_a_marca(db_session):
    """A escrita não deve reagregar a view (custa ~1,4s com dados reais); ela
    apenas marca, e a leitura seguinte de /fluxo é quem atualiza."""
    from sqlalchemy import text

    from app.sql_views import CONTROLE_TABLE, garantir_fluxo_atualizado, marcar_fluxo_desatualizado

    def marca_atual():
        return db_session.execute(
            text(f"SELECT precisa_atualizar FROM {CONTROLE_TABLE} WHERE id = 1")
        ).scalar()

    marcar_fluxo_desatualizado(db_session)
    assert marca_atual(), "a escrita precisa marcar a view como desatualizada"

    assert garantir_fluxo_atualizado(db_session) is True
    assert not marca_atual(), "a leitura precisa baixar a marca"

    # Sem nova escrita, uma segunda leitura não deve reagregar de novo.
    assert garantir_fluxo_atualizado(db_session) is False


def test_criar_registro_marca_view_como_desatualizada(db_session):
    from sqlalchemy import text

    from app.sql_views import CONTROLE_TABLE, garantir_fluxo_atualizado

    dados = setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    garantir_fluxo_atualizado(db_session)

    resposta = client.post(
        "/registros",
        headers=headers,
        json={
            "data_vacinacao": "2024-07-01",
            "municipio_vacina_id": "2304400",
            "municipio_residencia_id": "2303709",
            # O id vem do fixture: no PostgreSQL a sequência de `vacinas` não
            # volta atrás no rollback entre testes, então não dá para supor 1.
            "vacina_id": dados["covid"].id,
            "idade": 40,
            "quantidade": 1,
        },
    )
    assert resposta.status_code == 201

    marca = db_session.execute(
        text(f"SELECT precisa_atualizar FROM {CONTROLE_TABLE} WHERE id = 1")
    ).scalar()
    assert marca, "criar registro deve marcar a view de fluxo para atualização"


def test_intermunicipal_pagina_e_respeita_teto_de_page_size(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    resposta = client.get("/fluxo/intermunicipal", headers=headers, params={"page_size": 100000})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["page_size"] <= 200, "page_size precisa ser limitado no servidor"
    assert corpo["total"] == 2
    assert corpo["page"] == 1
    assert "total_doses" in corpo


def test_intermunicipal_ordena_do_maior_fluxo_para_o_menor(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get("/fluxo/intermunicipal", headers=headers).json()["items"]

    doses = [item["total_doses"] for item in itens]
    assert doses == sorted(doses, reverse=True)
    assert itens[0]["municipio_origem_id"] == "2308009"  # 5 doses > 3 doses


def test_intermunicipal_filtra_por_municipio(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get(
        "/fluxo/intermunicipal", headers=headers, params={"municipio_id": "2303709"}
    ).json()

    assert corpo["total"] == 1
    assert corpo["items"][0]["municipio_origem_id"] == "2303709"


def test_ranking_respeita_teto_do_limit(db_session):
    setup_fluxo_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/fluxo/ranking", headers=headers, params={"limit": 100000}).json()

    assert len(corpo["top_polo"]) <= 50
    assert len(corpo["top_evasao"]) <= 50
