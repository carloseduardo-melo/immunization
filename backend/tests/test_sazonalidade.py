"""RF17 - Cobre o painel de sazonalidade (/sazonalidade)."""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash

client = TestClient(app)


def auth_headers(db_session, email="sazonalidade@example.com", role="ADMIN"):
    db_session.add(
        UsuarioAdmin(email=email, senha_hash=get_password_hash("senha123"), role=role)
    )
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def setup_dados(db_session):
    """Jan = 15, Mar = 50 (30 de 2024 + 20 de 2023), Jul = 2. Total = 67."""
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
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 10), vacina_id=covid.id,
                municipio_vacina_id="2304400", quantidade=10, status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 20), vacina_id=flu.id,
                municipio_vacina_id="2303709", quantidade=5, status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2024, 3, 5), vacina_id=covid.id,
                municipio_vacina_id="2304400", quantidade=30, status_dado="VALIDO",
            ),
            # Ano diferente, mesmo mês: soma na mesma barra de março.
            RegistroVacinacao(
                data_vacinacao=date(2023, 3, 5), vacina_id=covid.id,
                municipio_vacina_id="2304400", quantidade=20, status_dado="VALIDO",
            ),
            # Inconsistente entra: o mês vem de data_vacinacao, que é confiável.
            RegistroVacinacao(
                data_vacinacao=date(2024, 7, 1), vacina_id=flu.id,
                municipio_vacina_id="2304400", quantidade=2,
                status_dado="DADO_INCONSISTENTE",
            ),
            # Inativo nunca entra.
            RegistroVacinacao(
                data_vacinacao=date(2024, 8, 1), vacina_id=covid.id,
                municipio_vacina_id="2304400", quantidade=99, status_dado="VALIDO",
                ativo=False,
            ),
        ]
    )
    db_session.commit()
    return covid, flu


def setup_ano_completo(db_session):
    """Doze meses de 2024 com 10, 20, ... 120 doses. Total = 780."""
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.commit()
    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, mes, 15),
                municipio_vacina_id="2304400",
                quantidade=mes * 10,
                status_dado="VALIDO",
            )
            for mes in range(1, 13)
        ]
    )
    db_session.commit()


def test_sem_token_retorna_401():
    assert client.get("/sazonalidade").status_code == 401


def test_retorna_sempre_os_doze_meses(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    meses = client.get("/sazonalidade", headers=headers).json()["meses"]

    assert [m["mes"] for m in meses] == list(range(1, 13))
    assert meses[0]["nome_mes"] == "Jan"
    assert meses[11]["nome_mes"] == "Dez"


def test_soma_o_volume_por_mes_do_ano(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/sazonalidade", headers=headers).json()
    totais = {m["mes"]: m["total_doses"] for m in corpo["meses"]}

    assert totais[1] == 15, "10 + 5"
    assert totais[3] == 50, "30 de 2024 + 20 de 2023 caem na mesma barra"
    assert totais[7] == 2, "DADO_INCONSISTENTE conta no volume"
    assert totais[8] == 0, "o registro inativo fica de fora"
    assert corpo["kpis"]["total_periodo"] == 67


def test_indice_de_sazonalidade_usa_media_de_doze_meses(db_session):
    setup_ano_completo(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/sazonalidade", headers=headers).json()
    meses = {m["mes"]: m for m in corpo["meses"]}

    assert corpo["kpis"]["media_mensal"] == 65.0, "780 / 12"
    assert meses[12]["indice_sazonalidade"] == round(120 / 65, 2)
    assert meses[1]["indice_sazonalidade"] == round(10 / 65, 2)


def test_pico_vale_e_amplitude(db_session):
    setup_ano_completo(db_session)
    headers = auth_headers(db_session)

    kpis = client.get("/sazonalidade", headers=headers).json()["kpis"]

    assert kpis["mes_pico"] == 12
    assert kpis["mes_pico_nome"] == "Dez"
    assert kpis["mes_vale"] == 1
    assert kpis["mes_vale_nome"] == "Jan"
    assert kpis["amplitude"] == 12.0, "120 / 10"


def test_empate_resolve_pelo_menor_mes(db_session):
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.commit()
    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 5), municipio_vacina_id="2304400",
                quantidade=100, status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2024, 2, 5), municipio_vacina_id="2304400",
                quantidade=100, status_dado="VALIDO",
            ),
        ]
    )
    db_session.commit()
    headers = auth_headers(db_session)

    kpis = client.get("/sazonalidade", headers=headers).json()["kpis"]

    assert kpis["mes_pico"] == 1, "empate no topo vence o mês mais cedo no ano"
    assert kpis["mes_vale"] == 3, "primeiro mês zerado"
    assert kpis["amplitude"] == 0.0, "vale zerado não divide por zero"


def test_filtra_por_vacina(db_session):
    covid, _ = setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get(
        "/sazonalidade", params={"vacina_id": covid.id}, headers=headers
    ).json()
    totais = {m["mes"]: m["total_doses"] for m in corpo["meses"]}

    assert totais[1] == 10
    assert totais[3] == 50
    assert totais[7] == 0, "julho é só da Influenza"


def test_filtra_por_municipio_de_aplicacao(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get(
        "/sazonalidade", params={"municipio_id": "2303709"}, headers=headers
    ).json()

    assert corpo["kpis"]["total_periodo"] == 5


def test_filtra_por_faixa_de_anos(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    so_2024 = client.get(
        "/sazonalidade", params={"ano_inicio": 2024}, headers=headers
    ).json()
    so_2023 = client.get(
        "/sazonalidade", params={"ano_fim": 2023}, headers=headers
    ).json()

    assert {m["mes"]: m["total_doses"] for m in so_2024["meses"]}[3] == 30
    assert so_2023["kpis"]["total_periodo"] == 20


def test_base_vazia_devolve_zeros(db_session):
    headers = auth_headers(db_session)

    corpo = client.get("/sazonalidade", headers=headers).json()

    assert corpo["kpis"]["total_periodo"] == 0
    assert corpo["kpis"]["media_mensal"] == 0.0
    assert corpo["kpis"]["mes_pico"] is None
    assert corpo["kpis"]["mes_pico_nome"] is None
    assert corpo["kpis"]["mes_vale"] is None
    assert corpo["kpis"]["mes_vale_nome"] is None
    assert corpo["kpis"]["amplitude"] == 0.0
    assert [m["total_doses"] for m in corpo["meses"]] == [0] * 12
    assert [m["indice_sazonalidade"] for m in corpo["meses"]] == [0.0] * 12
