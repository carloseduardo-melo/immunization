"""RF21 (log automático em Update/Delete), RF22 (consulta com filtros) e
RNF09 (imutabilidade do log)."""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import LogAuditoria, Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash
from app.services import auditoria

client = TestClient(app)


def _usuario(db_session, email="admin@example.com", role="ADMIN", municipio_id=None):
    usuario = UsuarioAdmin(
        email=email,
        senha_hash=get_password_hash("senha123"),
        role=role,
        municipio_alocado_id=municipio_id,
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


def _headers(db_session, email="admin@example.com", role="ADMIN", municipio_id=None):
    _usuario(db_session, email=email, role=role, municipio_id=municipio_id)
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _municipio(db_session, id_ibge="2304400", nome="Fortaleza"):
    municipio = Municipio(id_ibge=id_ibge, nome=nome, uf="CE")
    db_session.add(municipio)
    db_session.commit()
    return municipio


def _vacina(db_session, nome="BCG"):
    vacina = Vacina(nome=nome)
    db_session.add(vacina)
    db_session.commit()
    db_session.refresh(vacina)
    return vacina


def _log(db_session, usuario, tabela="municipios", acao="UPDATE", criado_em=None,
         registro_id="2304400"):
    log = LogAuditoria(
        tabela=tabela,
        registro_id=registro_id,
        acao=acao,
        usuario_id=usuario.id,
        valores_antigos={"nome": "Antes"},
        valores_novos={"nome": "Depois"},
        criado_em=criado_em or datetime(2026, 8, 20, 12, 0, 0),
    )
    db_session.add(log)
    db_session.commit()
    return log


# ==========================================
# RF21 - gravação automática na camada de serviço
# ==========================================


def test_serializar_converte_valores_para_json(db_session):
    _municipio(db_session)
    registro = RegistroVacinacao(
        data_vacinacao=date(2026, 8, 14),
        municipio_vacina_id="2304400",
        quantidade=2,
    )
    db_session.add(registro)
    db_session.commit()

    snapshot = auditoria.serializar(registro)

    assert snapshot["data_vacinacao"] == "2026-08-14"
    assert snapshot["id"] == str(registro.id)
    assert snapshot["quantidade"] == 2


def test_registrar_grava_linha_sem_commit(db_session):
    usuario = _usuario(db_session)

    auditoria.registrar(
        db_session,
        tabela="vacinas",
        registro_id=7,
        acao="UPDATE",
        usuario=usuario,
        valores_antigos={"nome": "A"},
        valores_novos={"nome": "B"},
    )
    db_session.commit()

    log = db_session.query(LogAuditoria).one()
    assert log.tabela == "vacinas"
    # O id chega como int e precisa caber na coluna de texto, que também
    # guarda id_ibge (string) e o UUID dos registros de vacinação.
    assert log.registro_id == "7"
    assert log.acao == "UPDATE"
    assert log.usuario_id == usuario.id


def test_update_de_municipio_grava_log(db_session):
    headers = _headers(db_session)
    _municipio(db_session)

    resposta = client.put(
        "/municipios/2304400",
        headers=headers,
        json={"nome": "Fortaleza Norte", "uf": "CE", "regiao_saude": None, "polo": True},
    )

    assert resposta.status_code == 200
    log = db_session.query(LogAuditoria).one()
    assert log.tabela == "municipios"
    assert log.registro_id == "2304400"
    assert log.acao == "UPDATE"
    assert log.valores_antigos["nome"] == "Fortaleza"
    assert log.valores_novos["nome"] == "Fortaleza Norte"
    assert log.valores_novos["polo"] is True


def test_delete_de_municipio_grava_log(db_session):
    headers = _headers(db_session)
    _municipio(db_session)

    resposta = client.delete("/municipios/2304400", headers=headers)

    assert resposta.status_code == 200
    log = db_session.query(LogAuditoria).one()
    assert log.tabela == "municipios"
    assert log.acao == "DELETE"
    assert log.valores_antigos["ativo"] is True
    assert log.valores_novos["ativo"] is False


def test_update_de_vacina_grava_log(db_session):
    headers = _headers(db_session)
    vacina = _vacina(db_session)

    resposta = client.put(
        f"/vacinas/{vacina.id}",
        headers=headers,
        json={"nome": "BCG ID", "alta_complexidade": True},
    )

    assert resposta.status_code == 200
    log = db_session.query(LogAuditoria).one()
    assert log.tabela == "vacinas"
    assert log.registro_id == str(vacina.id)
    assert log.acao == "UPDATE"
    assert log.valores_antigos["nome"] == "BCG"
    assert log.valores_novos["nome"] == "BCG ID"
    assert log.valores_novos["alta_complexidade"] is True


def test_delete_de_vacina_grava_log(db_session):
    headers = _headers(db_session)
    vacina = _vacina(db_session)

    resposta = client.delete(f"/vacinas/{vacina.id}", headers=headers)

    assert resposta.status_code == 200
    log = db_session.query(LogAuditoria).one()
    assert log.tabela == "vacinas"
    assert log.acao == "DELETE"
    assert log.valores_antigos["ativo"] is True
    assert log.valores_novos["ativo"] is False


def test_criacao_nao_gera_log(db_session):
    """O RF21 cobre apenas Update e Delete."""
    headers = _headers(db_session)

    client.post(
        "/municipios",
        headers=headers,
        json={"id_ibge": "2304400", "nome": "Fortaleza", "uf": "CE", "polo": False},
    )

    assert db_session.query(LogAuditoria).count() == 0


# ==========================================
# RF22 - consulta com filtros
# ==========================================


def test_listar_auditoria_traz_email_do_usuario(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    _log(db_session, usuario)

    resposta = client.get("/auditoria", headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["usuario_email"] == "admin@example.com"
    assert corpo["items"][0]["valores_antigos"] == {"nome": "Antes"}
    assert corpo["items"][0]["valores_novos"] == {"nome": "Depois"}


def test_listar_auditoria_ordena_do_mais_recente_para_o_mais_antigo(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    _log(db_session, usuario, criado_em=datetime(2026, 1, 1, 10, 0), registro_id="antigo")
    _log(db_session, usuario, criado_em=datetime(2026, 6, 1, 10, 0), registro_id="recente")

    itens = client.get("/auditoria", headers=headers).json()["items"]

    assert [item["registro_id"] for item in itens] == ["recente", "antigo"]


def test_filtro_por_tabela(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    _log(db_session, usuario, tabela="municipios")
    _log(db_session, usuario, tabela="vacinas", registro_id="1")

    corpo = client.get("/auditoria", headers=headers, params={"tabela": "vacinas"}).json()

    assert corpo["total"] == 1
    assert corpo["items"][0]["tabela"] == "vacinas"


def test_filtro_por_usuario(db_session):
    headers = _headers(db_session)
    autor = db_session.query(UsuarioAdmin).one()
    outro = _usuario(db_session, email="outro@example.com", role="GESTOR_ESTADUAL")
    _log(db_session, autor)
    _log(db_session, outro, registro_id="2303709")

    corpo = client.get(
        "/auditoria", headers=headers, params={"usuario_id": str(outro.id)}
    ).json()

    assert corpo["total"] == 1
    assert corpo["items"][0]["usuario_email"] == "outro@example.com"


def test_filtro_por_periodo_inclui_os_dois_extremos(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    _log(db_session, usuario, criado_em=datetime(2026, 3, 1, 0, 0), registro_id="antes")
    _log(db_session, usuario, criado_em=datetime(2026, 3, 10, 23, 59), registro_id="dentro")
    _log(db_session, usuario, criado_em=datetime(2026, 3, 20, 0, 0), registro_id="depois")

    corpo = client.get(
        "/auditoria",
        headers=headers,
        params={"data_inicio": "2026-03-01", "data_fim": "2026-03-10"},
    ).json()

    assert {item["registro_id"] for item in corpo["items"]} == {"antes", "dentro"}


def test_filtros_combinados(db_session):
    headers = _headers(db_session)
    autor = db_session.query(UsuarioAdmin).one()
    outro = _usuario(db_session, email="outro@example.com", role="ADMIN")
    _log(db_session, autor, tabela="vacinas", criado_em=datetime(2026, 5, 5), registro_id="alvo")
    _log(db_session, outro, tabela="vacinas", criado_em=datetime(2026, 5, 5), registro_id="x")
    _log(db_session, autor, tabela="municipios", criado_em=datetime(2026, 5, 5), registro_id="y")
    _log(db_session, autor, tabela="vacinas", criado_em=datetime(2026, 9, 9), registro_id="z")

    corpo = client.get(
        "/auditoria",
        headers=headers,
        params={
            "usuario_id": str(autor.id),
            "tabela": "vacinas",
            "data_inicio": "2026-05-01",
            "data_fim": "2026-05-31",
        },
    ).json()

    assert corpo["total"] == 1
    assert corpo["items"][0]["registro_id"] == "alvo"


def test_paginacao_da_auditoria(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    for indice in range(5):
        _log(
            db_session,
            usuario,
            criado_em=datetime(2026, 4, 1, 10, indice),
            registro_id=str(indice),
        )

    corpo = client.get(
        "/auditoria", headers=headers, params={"page": 2, "page_size": 2}
    ).json()

    assert corpo["total"] == 5
    assert corpo["total_pages"] == 3
    assert corpo["page"] == 2
    assert len(corpo["items"]) == 2


def test_paginacao_normaliza_valores_invalidos(db_session):
    headers = _headers(db_session)

    corpo = client.get(
        "/auditoria", headers=headers, params={"page": 0, "page_size": 0}
    ).json()

    assert corpo["page"] == 1
    assert corpo["page_size"] == 10


def test_page_size_tem_teto_de_100(db_session):
    headers = _headers(db_session)

    corpo = client.get("/auditoria", headers=headers, params={"page_size": 500}).json()

    assert corpo["page_size"] == 100


def test_usuarios_da_auditoria_lista_apenas_quem_tem_log(db_session):
    headers = _headers(db_session)
    autor = db_session.query(UsuarioAdmin).one()
    _usuario(db_session, email="sem-log@example.com", role="ADMIN")
    _log(db_session, autor)
    _log(db_session, autor, registro_id="2303709")

    corpo = client.get("/auditoria/usuarios", headers=headers).json()

    assert corpo == [{"id": str(autor.id), "email": "admin@example.com"}]


# ==========================================
# RF22 - acesso restrito ao perfil Administrador
# ==========================================


def test_gestor_estadual_nao_acessa_auditoria(db_session):
    headers = _headers(db_session, email="estadual@example.com", role="GESTOR_ESTADUAL")

    assert client.get("/auditoria", headers=headers).status_code == 403
    assert client.get("/auditoria/usuarios", headers=headers).status_code == 403


def test_gestor_municipal_nao_acessa_auditoria(db_session):
    headers = _headers(
        db_session,
        email="municipal@example.com",
        role="GESTOR_MUNICIPAL",
        municipio_id="2304400",
    )

    assert client.get("/auditoria", headers=headers).status_code == 403


def test_auditoria_exige_token():
    assert client.get("/auditoria").status_code == 401


# ==========================================
# RNF09 - imutabilidade
# ==========================================


def test_api_nao_expoe_nenhuma_rota_de_escrita_em_auditoria():
    metodos_de_escrita = {"POST", "PUT", "PATCH", "DELETE"}
    for rota in app.routes:
        caminho = getattr(rota, "path", "")
        if caminho.startswith("/auditoria"):
            assert not (getattr(rota, "methods", set()) & metodos_de_escrita), caminho


def test_metodos_de_escrita_em_auditoria_sao_recusados(db_session):
    headers = _headers(db_session)
    usuario = db_session.query(UsuarioAdmin).one()
    log = _log(db_session, usuario)

    respostas = (
        client.post("/auditoria", headers=headers, json={}),
        client.put(f"/auditoria/{log.id}", headers=headers, json={}),
        client.patch(f"/auditoria/{log.id}", headers=headers, json={}),
        client.delete(f"/auditoria/{log.id}", headers=headers),
    )
    for resposta in respostas:
        assert resposta.status_code in (404, 405)

    assert db_session.query(LogAuditoria).count() == 1


def test_politica_de_retencao_minima_e_de_30_dias():
    assert auditoria.RETENCAO_DIAS_MINIMA == 30


def test_expurgo_recusa_janela_menor_que_a_retencao_minima(db_session):
    usuario = _usuario(db_session)
    _log(db_session, usuario, criado_em=datetime.utcnow() - timedelta(days=90))

    try:
        auditoria.expurgar_logs_antigos(db_session, dias=29)
    except ValueError as exc:
        assert "30" in str(exc)
    else:  # pragma: no cover - o expurgo precisa recusar a janela curta
        raise AssertionError("expurgar_logs_antigos deveria recusar dias < 30")

    assert db_session.query(LogAuditoria).count() == 1


def test_expurgo_remove_apenas_o_que_passou_da_retencao(db_session):
    usuario = _usuario(db_session)
    _log(
        db_session,
        usuario,
        criado_em=datetime.utcnow() - timedelta(days=400),
        registro_id="velho",
    )
    _log(
        db_session,
        usuario,
        criado_em=datetime.utcnow() - timedelta(days=5),
        registro_id="novo",
    )

    removidos = auditoria.expurgar_logs_antigos(db_session, dias=365)

    assert removidos == 1
    assert [log.registro_id for log in db_session.query(LogAuditoria).all()] == ["novo"]
