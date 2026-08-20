from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import AlertaCompletude, Municipio, RegistroVacinacao, UsuarioAdmin
from app.security import get_password_hash
from app.services.completude import detectar_anomalias

client = TestClient(app)


def _criar_usuario(db_session, email, role, municipio_id=None):
    db_session.add(
        UsuarioAdmin(
            email=email,
            senha_hash=get_password_hash("senha123"),
            role=role,
            municipio_alocado_id=municipio_id,
        )
    )
    db_session.commit()


def _headers(db_session, role="ADMIN", email="admin@example.com", municipio_id=None):
    _criar_usuario(db_session, email, role, municipio_id)
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _municipio(db_session, id_ibge="2304400", nome="Fortaleza"):
    db_session.add(Municipio(id_ibge=id_ibge, nome=nome, uf="CE"))
    db_session.commit()


def _serie(db_session, municipio_id, totais_por_mes):
    """totais_por_mes: {(ano, mes): quantidade} -> um registro por mês."""
    for (ano, mes), quantidade in totais_por_mes.items():
        db_session.add(
            RegistroVacinacao(
                data_vacinacao=date(ano, mes, 15),
                municipio_vacina_id=municipio_id,
                quantidade=quantidade,
            )
        )
    db_session.commit()


def test_queda_brusca_em_um_mes_gera_alerta(db_session):
    _municipio(db_session)
    _serie(
        db_session,
        "2304400",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 4): 100,
            (2024, 5): 100,
            (2024, 6): 10,
        },
    )

    resultado = detectar_anomalias(db_session)

    alertas = db_session.query(AlertaCompletude).all()
    assert len(alertas) == 1
    assert (alertas[0].referencia_ano, alertas[0].referencia_mes) == (2024, 6)
    assert alertas[0].total_observado == 10
    assert alertas[0].status == "ABERTO"
    assert resultado.alertas_criados == 1
    assert resultado.alertas_atualizados == 0
    assert resultado.municipios_analisados == 1
    assert resultado.meses_analisados == 6


def test_serie_estavel_nao_gera_alerta(db_session):
    _municipio(db_session, "2303709", "Caucaia")
    _serie(
        db_session,
        "2303709",
        {(2024, 1): 100, (2024, 2): 110, (2024, 3): 90, (2024, 4): 105, (2024, 5): 95},
    )

    resultado = detectar_anomalias(db_session)

    assert resultado.alertas_criados == 0
    assert db_session.query(AlertaCompletude).count() == 0


def test_mes_ausente_no_meio_do_historico_vira_alerta_com_total_zero(db_session):
    _municipio(db_session, "2308009", "Maracanaú")
    _serie(
        db_session,
        "2308009",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 5): 100,
            (2024, 6): 100,
            (2024, 7): 100,
        },
    )

    detectar_anomalias(db_session)

    alerta = db_session.query(AlertaCompletude).one()
    assert (alerta.referencia_ano, alerta.referencia_mes) == (2024, 4)
    assert alerta.total_observado == 0


def test_municipio_com_historico_curto_e_ignorado(db_session):
    _municipio(db_session, "2301000", "Aracati")
    _serie(db_session, "2301000", {(2024, 1): 100, (2024, 2): 5})

    resultado = detectar_anomalias(db_session)

    assert resultado.municipios_analisados == 0
    assert db_session.query(AlertaCompletude).count() == 0


def test_k_maior_torna_a_deteccao_menos_sensivel(db_session):
    _municipio(db_session, "2312908", "Sobral")
    _serie(
        db_session,
        "2312908",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 4): 100,
            (2024, 5): 100,
            (2024, 6): 10,
        },
    )

    resultado = detectar_anomalias(db_session, k=3.0)

    assert resultado.alertas_criados == 0


def test_reexecutar_nao_duplica_e_preserva_status_tratado(db_session):
    _municipio(db_session, "2307304", "Juazeiro do Norte")
    _serie(
        db_session,
        "2307304",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 4): 100,
            (2024, 5): 100,
            (2024, 6): 10,
        },
    )

    detectar_anomalias(db_session)
    alerta = db_session.query(AlertaCompletude).one()
    alerta.status = "RESOLVIDO"
    db_session.commit()

    resultado = detectar_anomalias(db_session)

    alertas = db_session.query(AlertaCompletude).all()
    assert len(alertas) == 1
    assert alertas[0].status == "RESOLVIDO"
    assert resultado.alertas_criados == 0
    assert resultado.alertas_atualizados == 1


def test_recalcular_como_admin_retorna_contadores(db_session):
    _municipio(db_session)
    _serie(
        db_session,
        "2304400",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 4): 100,
            (2024, 5): 100,
            (2024, 6): 10,
        },
    )
    headers = _headers(db_session)

    resposta = client.post("/completude/recalcular", headers=headers)

    assert resposta.status_code == 200
    assert resposta.json()["alertas_criados"] == 1


def test_recalcular_aceita_k_customizado(db_session):
    _municipio(db_session)
    _serie(
        db_session,
        "2304400",
        {
            (2024, 1): 100,
            (2024, 2): 100,
            (2024, 3): 100,
            (2024, 4): 100,
            (2024, 5): 100,
            (2024, 6): 10,
        },
    )
    headers = _headers(db_session)

    resposta = client.post("/completude/recalcular", params={"k": 3.0}, headers=headers)

    assert resposta.status_code == 200
    assert resposta.json()["alertas_criados"] == 0


def test_recalcular_negado_para_gestor_estadual(db_session):
    headers = _headers(db_session, role="GESTOR_ESTADUAL", email="estadual@example.com")

    resposta = client.post("/completude/recalcular", headers=headers)

    assert resposta.status_code == 403


def test_recalcular_negado_para_gestor_municipal(db_session):
    _municipio(db_session)
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="municipal@example.com",
        municipio_id="2304400",
    )

    resposta = client.post("/completude/recalcular", headers=headers)

    assert resposta.status_code == 403


def test_recalcular_sem_token_retorna_401():
    resposta = client.post("/completude/recalcular")

    assert resposta.status_code == 401
