from datetime import date

import pytest
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


def test_registro_inativo_nao_conta_na_completude(db_session):
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
    # Registro inativo no mesmo mês da queda: se contasse, o total observado
    # subiria bem acima do limite inferior e o alerta não seria gerado.
    db_session.add(
        RegistroVacinacao(
            data_vacinacao=date(2024, 6, 20),
            municipio_vacina_id="2304400",
            quantidade=1000,
            ativo=False,
        )
    )
    db_session.commit()

    resultado = detectar_anomalias(db_session)

    alerta = db_session.query(AlertaCompletude).one()
    assert alerta.total_observado == 10
    assert resultado.alertas_criados == 1


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


@pytest.mark.parametrize("k_invalido", [0, -1])
def test_recalcular_k_fora_do_intervalo_retorna_422(db_session, k_invalido):
    headers = _headers(db_session)

    resposta = client.post("/completude/recalcular", params={"k": k_invalido}, headers=headers)

    assert resposta.status_code == 422


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


def _alerta(db_session, ano=2024, mes=9, municipio_id="2304400", status="ABERTO", total=10):
    alerta = AlertaCompletude(
        referencia_ano=ano,
        referencia_mes=mes,
        municipio_id=municipio_id,
        total_observado=total,
        status=status,
    )
    db_session.add(alerta)
    db_session.commit()
    db_session.refresh(alerta)
    return alerta


def test_listar_alertas_retorna_itens_com_nome_do_municipio(db_session):
    _municipio(db_session)
    _alerta(db_session)
    headers = _headers(db_session)

    resposta = client.get("/completude/alertas", headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["municipio_nome"] == "Fortaleza"
    assert corpo["items"][0]["status"] == "ABERTO"
    assert corpo["totais_por_status"]["ABERTO"] == 1
    assert corpo["totais_por_status"]["RESOLVIDO"] == 0
    assert corpo["municipios_afetados"] == 1


def test_listar_alertas_sem_municipio_vinculado(db_session):
    _alerta(db_session, municipio_id=None)
    headers = _headers(db_session)

    resposta = client.get("/completude/alertas", headers=headers)

    assert resposta.json()["items"][0]["municipio_nome"] is None


def test_listar_alertas_filtra_por_status(db_session):
    _municipio(db_session)
    _alerta(db_session, mes=9, status="ABERTO")
    _alerta(db_session, mes=10, status="RESOLVIDO")
    headers = _headers(db_session)

    resposta = client.get("/completude/alertas", params={"status": "RESOLVIDO"}, headers=headers)

    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["referencia_mes"] == 10
    # Os KPIs ignoram o filtro de status: continuam contando os dois alertas.
    assert corpo["totais_por_status"]["ABERTO"] == 1
    assert corpo["totais_por_status"]["RESOLVIDO"] == 1


def test_listar_alertas_status_invalido_retorna_422(db_session):
    headers = _headers(db_session)

    resposta = client.get("/completude/alertas", params={"status": "FOO"}, headers=headers)

    assert resposta.status_code == 422


@pytest.mark.parametrize("valor", ["ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"])
def test_listar_alertas_aceita_cada_status_valido(db_session, valor):
    headers = _headers(db_session)

    resposta = client.get("/completude/alertas", params={"status": valor}, headers=headers)

    assert resposta.status_code == 200


def test_listar_alertas_filtra_por_municipio_e_ano(db_session):
    _municipio(db_session)
    _municipio(db_session, "2303709", "Caucaia")
    _alerta(db_session, ano=2024, mes=9, municipio_id="2304400")
    _alerta(db_session, ano=2023, mes=9, municipio_id="2303709")
    headers = _headers(db_session)

    por_municipio = client.get(
        "/completude/alertas", params={"municipio_id": "2303709"}, headers=headers
    ).json()
    por_ano = client.get("/completude/alertas", params={"ano": 2024}, headers=headers).json()

    assert por_municipio["total"] == 1
    assert por_municipio["items"][0]["municipio_id"] == "2303709"
    assert por_ano["total"] == 1
    assert por_ano["items"][0]["referencia_ano"] == 2024


def test_listar_alertas_ordena_do_mais_recente_para_o_mais_antigo(db_session):
    _municipio(db_session)
    _alerta(db_session, ano=2023, mes=5)
    _alerta(db_session, ano=2024, mes=2)
    _alerta(db_session, ano=2024, mes=9)
    headers = _headers(db_session)

    itens = client.get("/completude/alertas", headers=headers).json()["items"]

    assert [(i["referencia_ano"], i["referencia_mes"]) for i in itens] == [
        (2024, 9),
        (2024, 2),
        (2023, 5),
    ]


def test_listar_alertas_paginacao_estavel_com_empate_de_ano_e_mes(db_session):
    """Vários alertas no mesmo (ano, mês) — sem desempate por id, a mesma
    linha pode aparecer em duas páginas ou nunca aparecer."""
    _municipio(db_session)
    ids_criados = {str(_alerta(db_session, mes=9, total=i).id) for i in range(1, 5)}
    headers = _headers(db_session)

    pagina1 = client.get(
        "/completude/alertas", params={"page": 1, "page_size": 2}, headers=headers
    ).json()
    pagina2 = client.get(
        "/completude/alertas", params={"page": 2, "page_size": 2}, headers=headers
    ).json()

    ids_retornados = [item["id"] for item in pagina1["items"] + pagina2["items"]]
    assert len(ids_retornados) == len(set(ids_retornados)) == 4
    assert set(ids_retornados) == ids_criados


def test_listar_alertas_pagina_e_normaliza_parametros_invalidos(db_session):
    _municipio(db_session)
    for mes in range(1, 13):
        _alerta(db_session, mes=mes)
    headers = _headers(db_session)

    pagina = client.get(
        "/completude/alertas", params={"page": 0, "page_size": 0}, headers=headers
    ).json()
    teto = client.get("/completude/alertas", params={"page_size": 500}, headers=headers).json()

    assert pagina["page"] == 1
    assert pagina["page_size"] == 10
    assert pagina["total"] == 12
    assert pagina["total_pages"] == 2
    assert len(pagina["items"]) == 10
    assert teto["page_size"] == 100


def test_listar_alertas_vazio_tem_zero_paginas(db_session):
    headers = _headers(db_session)

    corpo = client.get("/completude/alertas", headers=headers).json()

    assert corpo["total"] == 0
    assert corpo["total_pages"] == 0
    assert corpo["municipios_afetados"] == 0


def test_gestor_estadual_ve_todos_os_alertas(db_session):
    _municipio(db_session)
    _municipio(db_session, "2303709", "Caucaia")
    _alerta(db_session, municipio_id="2304400")
    _alerta(db_session, municipio_id="2303709")
    headers = _headers(db_session, role="GESTOR_ESTADUAL", email="estadual@example.com")

    assert client.get("/completude/alertas", headers=headers).json()["total"] == 2


def test_gestor_municipal_ve_apenas_o_municipio_alocado(db_session):
    _municipio(db_session)
    _municipio(db_session, "2303709", "Caucaia")
    _alerta(db_session, municipio_id="2304400")
    _alerta(db_session, municipio_id="2303709")
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="municipal@example.com",
        municipio_id="2303709",
    )

    corpo = client.get("/completude/alertas", headers=headers).json()

    assert corpo["total"] == 1
    assert corpo["items"][0]["municipio_id"] == "2303709"


def test_gestor_municipal_pode_consultar_o_proprio_municipio(db_session):
    """Caminho de permissão de validate_municipio_scope: pedir explicitamente
    o próprio municipio_alocado_id não é bloqueado."""
    _municipio(db_session)
    _municipio(db_session, "2303709", "Caucaia")
    _alerta(db_session, municipio_id="2304400")
    _alerta(db_session, municipio_id="2303709")
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="municipal@example.com",
        municipio_id="2304400",
    )

    resposta = client.get(
        "/completude/alertas", params={"municipio_id": "2304400"}, headers=headers
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["municipio_id"] == "2304400"


def test_gestor_municipal_nao_consulta_outro_municipio(db_session):
    _municipio(db_session)
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="municipal@example.com",
        municipio_id="2303709",
    )

    resposta = client.get(
        "/completude/alertas", params={"municipio_id": "2304400"}, headers=headers
    )

    assert resposta.status_code == 403


def test_listar_alertas_sem_token_retorna_401():
    assert client.get("/completude/alertas").status_code == 401


@pytest.mark.parametrize("novo_status", ["INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"])
def test_admin_altera_status_do_alerta(db_session, novo_status):
    _municipio(db_session)
    alerta = _alerta(db_session)
    headers = _headers(db_session)

    resposta = client.put(
        f"/completude/alertas/{alerta.id}", json={"status": novo_status}, headers=headers
    )

    assert resposta.status_code == 200
    assert resposta.json()["status"] == novo_status
    db_session.refresh(alerta)
    assert alerta.status == novo_status


def test_alterar_status_negado_para_gestor_estadual(db_session):
    _municipio(db_session)
    alerta = _alerta(db_session)
    headers = _headers(db_session, role="GESTOR_ESTADUAL", email="estadual@example.com")

    resposta = client.put(
        f"/completude/alertas/{alerta.id}", json={"status": "RESOLVIDO"}, headers=headers
    )

    assert resposta.status_code == 403
    db_session.refresh(alerta)
    assert alerta.status == "ABERTO"


def test_alterar_status_negado_para_gestor_municipal(db_session):
    _municipio(db_session)
    alerta = _alerta(db_session)
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="municipal@example.com",
        municipio_id="2304400",
    )

    resposta = client.put(
        f"/completude/alertas/{alerta.id}", json={"status": "RESOLVIDO"}, headers=headers
    )

    assert resposta.status_code == 403


def test_alterar_status_invalido_retorna_422(db_session):
    _municipio(db_session)
    alerta = _alerta(db_session)
    headers = _headers(db_session)

    resposta = client.put(
        f"/completude/alertas/{alerta.id}", json={"status": "ARQUIVADO"}, headers=headers
    )

    assert resposta.status_code == 422


def test_alterar_status_de_alerta_inexistente_retorna_404(db_session):
    headers = _headers(db_session)

    resposta = client.put(
        "/completude/alertas/00000000-0000-0000-0000-000000000000",
        json={"status": "RESOLVIDO"},
        headers=headers,
    )

    assert resposta.status_code == 404


def test_alterar_status_sem_token_retorna_401():
    resposta = client.put(
        "/completude/alertas/00000000-0000-0000-0000-000000000000",
        json={"status": "RESOLVIDO"},
    )

    assert resposta.status_code == 401
