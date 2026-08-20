"""RF23 - Cobre os KPIs e a série temporal de /dashboard/resumo."""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash

client = TestClient(app)


def auth_headers(db_session, email="dashboard@example.com", role="ADMIN"):
    db_session.add(
        UsuarioAdmin(email=email, senha_hash=get_password_hash("senha123"), role=role)
    )
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_dados(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    covid = Vacina(nome="COVID-19")
    flu = Vacina(nome="Influenza")
    db_session.add_all([covid, flu])
    db_session.commit()
    db_session.refresh(covid)
    db_session.refresh(flu)

    db_session.add_all(
        [
            # residente, sem deslocamento
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 10), vacina_id=covid.id,
                municipio_residencia_id="2304400", municipio_vacina_id="2304400",
                teve_deslocamento=False, quantidade=10, status_dado="VALIDO", idade=30,
            ),
            # deslocado
            RegistroVacinacao(
                data_vacinacao=date(2024, 2, 10), vacina_id=flu.id,
                municipio_residencia_id="2303709", municipio_vacina_id="2304400",
                teve_deslocamento=True, quantidade=5, status_dado="VALIDO", idade=40,
            ),
            # inconsistente: entra só no KPI de inconsistências
            RegistroVacinacao(
                data_vacinacao=date(2024, 3, 10), vacina_id=covid.id,
                municipio_residencia_id="2304400", municipio_vacina_id="2304400",
                teve_deslocamento=False, quantidade=2, status_dado="DADO_INCONSISTENTE",
                idade=200,
            ),
            # inativo: não deve ser contabilizado em nada
            RegistroVacinacao(
                data_vacinacao=date(2024, 4, 10), vacina_id=covid.id,
                municipio_residencia_id="2304400", municipio_vacina_id="2304400",
                teve_deslocamento=False, quantidade=99, status_dado="VALIDO",
                idade=30, ativo=False,
            ),
        ]
    )
    db_session.commit()
    return covid, flu


def test_resumo_calcula_kpis(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/dashboard/resumo", headers=headers).json()
    kpis = corpo["kpis"]

    assert kpis["total_doses"] == 17, "10 + 5 + 2; o registro inativo fica de fora"
    assert kpis["total_deslocamentos"] == 5
    assert kpis["total_inconsistentes"] == 2
    assert kpis["taxa_mobilidade"] == round(5 / 17 * 100, 2)


def test_resumo_monta_serie_temporal(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    grafico = client.get("/dashboard/resumo", headers=headers).json()["grafico"]

    assert grafico, "a série temporal não pode vir vazia com dados válidos"
    meses = {ponto["mes"] for ponto in grafico}
    assert "2024-01" in meses and "2024-02" in meses
    assert "2024-03" not in meses, "registros inconsistentes ficam fora do gráfico"


def test_resumo_filtra_por_municipio(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get(
        "/dashboard/resumo", headers=headers, params={"municipio_id": "2303709"}
    ).json()

    assert corpo["kpis"]["total_doses"] == 0, "nenhuma dose foi aplicada em Caucaia"


def test_resumo_filtra_por_vacina(db_session):
    covid, _ = setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get(
        "/dashboard/resumo", headers=headers, params={"vacina_id": covid.id}
    ).json()

    assert corpo["kpis"]["total_doses"] == 12  # 10 válidas + 2 inconsistentes
    assert corpo["kpis"]["total_deslocamentos"] == 0


def test_resumo_filtra_por_ano(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/dashboard/resumo", headers=headers, params={"ano": 2023}).json()

    assert corpo["kpis"]["total_doses"] == 0
    assert corpo["kpis"]["taxa_mobilidade"] == 0.0, "sem doses, a taxa não pode dividir por zero"


def test_resumo_sem_dados_nao_quebra(db_session):
    headers = auth_headers(db_session)

    corpo = client.get("/dashboard/resumo", headers=headers).json()

    assert corpo["kpis"]["total_doses"] == 0
    assert corpo["kpis"]["taxa_mobilidade"] == 0.0
    assert corpo["grafico"] == []


def test_resumo_exige_autenticacao():
    assert client.get("/dashboard/resumo").status_code == 401
