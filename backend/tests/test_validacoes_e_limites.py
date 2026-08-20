"""Cobre os validadores dos schemas, os limites de paginação dos routers e os
utilitários de app/sql_views.py e app/database.py."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.database import SessionLocal, ensure_default_admin_user, get_db, init_db
from app.main import app
from app.models import Municipio, UsuarioAdmin, Vacina
from app.schemas import MunicipioCreate, RegistroVacinacaoCreate, VacinaCreate
from app.security import get_password_hash
from app.sql_views import (
    CONTROLE_TABLE,
    VIEW_NAME,
    create_indexes_sql,
    create_view_sql,
    drop_view_sql,
    ensure_fluxo_view,
    garantir_fluxo_atualizado,
    marcar_fluxo_desatualizado,
)

client = TestClient(app)


def auth_headers(db_session, email="limites@example.com", role="ADMIN"):
    db_session.add(
        UsuarioAdmin(email=email, senha_hash=get_password_hash("senha123"), role=role)
    )
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# VALIDADORES DOS SCHEMAS
# ============================================================

@pytest.mark.parametrize("uf", ["C", "CEA", "C1", "12", ""])
def test_uf_invalida_e_rejeitada(uf):
    with pytest.raises(ValidationError, match="2 letras"):
        MunicipioCreate(id_ibge="2304400", nome="Fortaleza", uf=uf)


def test_uf_e_normalizada_para_maiuscula():
    assert MunicipioCreate(id_ibge="2304400", nome="Fortaleza", uf=" ce ").uf == "CE"


@pytest.mark.parametrize("id_ibge", ["123", "23044000", "abcdefg", ""])
def test_id_ibge_invalido_e_rejeitado(id_ibge):
    with pytest.raises(ValidationError, match="7 dígitos"):
        MunicipioCreate(id_ibge=id_ibge, nome="Fortaleza", uf="CE")


@pytest.mark.parametrize("nome", ["", "   "])
def test_nome_de_municipio_vazio_e_rejeitado(nome):
    with pytest.raises(ValidationError, match="obrigatório"):
        MunicipioCreate(id_ibge="2304400", nome=nome, uf="CE")


def test_nome_de_municipio_e_aparado():
    assert MunicipioCreate(id_ibge="2304400", nome="  Sobral  ", uf="CE").nome == "Sobral"


@pytest.mark.parametrize("nome", ["", "   "])
def test_nome_de_vacina_vazio_e_rejeitado(nome):
    with pytest.raises(ValidationError, match="obrigatório"):
        VacinaCreate(nome=nome)


def test_municipio_de_aplicacao_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="7 dígitos"):
        RegistroVacinacaoCreate(data_vacinacao="2024-01-01", municipio_vacina_id="123")


def test_municipio_de_residencia_vazio_vira_nulo():
    registro = RegistroVacinacaoCreate(
        data_vacinacao="2024-01-01", municipio_vacina_id="2304400",
        municipio_residencia_id="   ",
    )
    assert registro.municipio_residencia_id is None


def test_municipio_de_residencia_invalido_e_rejeitado():
    with pytest.raises(ValidationError, match="7 dígitos"):
        RegistroVacinacaoCreate(
            data_vacinacao="2024-01-01", municipio_vacina_id="2304400",
            municipio_residencia_id="99",
        )


@pytest.mark.parametrize("quantidade", [0, -1])
def test_quantidade_nao_positiva_e_rejeitada(quantidade):
    with pytest.raises(ValidationError, match="positivo"):
        RegistroVacinacaoCreate(
            data_vacinacao="2024-01-01", municipio_vacina_id="2304400",
            quantidade=quantidade,
        )


# ============================================================
# LIMITES DE PAGINAÇÃO DOS ROUTERS
# ============================================================

@pytest.mark.parametrize("rota", ["/municipios", "/vacinas", "/registros"])
def test_page_size_e_limitado_a_100(db_session, rota):
    headers = auth_headers(db_session, email=f"pag{rota.strip('/')}@example.com")

    corpo = client.get(rota, headers=headers, params={"page_size": 100000}).json()

    assert corpo["page_size"] == 100


@pytest.mark.parametrize("rota", ["/municipios", "/vacinas", "/registros"])
def test_page_e_page_size_invalidos_caem_no_padrao(db_session, rota):
    headers = auth_headers(db_session, email=f"neg{rota.strip('/')}@example.com")

    corpo = client.get(rota, headers=headers, params={"page": -5, "page_size": 0}).json()

    assert corpo["page"] == 1
    assert corpo["page_size"] == 10


def test_fluxo_normaliza_pagina_e_tamanho_invalidos(db_session):
    headers = auth_headers(db_session, email="fluxopag@example.com")

    corpo = client.get(
        "/fluxo/intermunicipal", headers=headers, params={"page": 0, "page_size": -1}
    ).json()

    assert corpo["page"] == 1
    assert corpo["page_size"] == 25


def test_ranking_normaliza_limite_invalido(db_session):
    headers = auth_headers(db_session, email="rankpag@example.com")

    resposta = client.get("/fluxo/ranking", headers=headers, params={"limit": 0})

    assert resposta.status_code == 200


def test_busca_de_registros_filtra_por_nome(db_session):
    headers = auth_headers(db_session, email="busca@example.com")
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.add(Vacina(nome="COVID-19"))
    db_session.commit()

    corpo = client.get("/registros", headers=headers, params={"search": "inexistente"}).json()

    assert corpo["total"] == 0


# ============================================================
# app/sql_views.py
# ============================================================

def test_ddl_muda_conforme_o_dialeto():
    assert "MATERIALIZED VIEW" in create_view_sql("postgresql")
    assert "MATERIALIZED" not in create_view_sql("sqlite")
    assert "MATERIALIZED VIEW" in drop_view_sql("postgresql")
    assert "MATERIALIZED" not in drop_view_sql("sqlite")


def test_indices_existem_apenas_no_postgres():
    indices = create_indexes_sql("postgresql")
    assert len(indices) == 4
    assert all(VIEW_NAME in sql for sql in indices)
    assert create_indexes_sql("sqlite") == []


def test_dialeto_e_resolvido_a_partir_da_sessao(db_session):
    """`_dialect_name` precisa funcionar tanto com Session quanto com Connection."""
    from app.sql_views import _dialect_name

    assert _dialect_name(db_session) == "sqlite"
    assert _dialect_name(db_session.get_bind()) == "sqlite"


def test_ensure_fluxo_view_e_idempotente():
    engine = create_engine("sqlite:///:memory:")
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_fluxo_view(conn)
        ensure_fluxo_view(conn)  # segunda chamada não pode falhar
        total = conn.execute(text(f"SELECT count(*) FROM {CONTROLE_TABLE}")).scalar()
    assert total == 1, "a tabela de controle deve ter exatamente uma linha"
    engine.dispose()


def test_marca_e_baixa_da_atualizacao(db_session):
    def marca():
        return db_session.execute(
            text(f"SELECT precisa_atualizar FROM {CONTROLE_TABLE} WHERE id = 1")
        ).scalar()

    garantir_fluxo_atualizado(db_session)
    assert not marca()

    marcar_fluxo_desatualizado(db_session)
    assert marca()

    assert garantir_fluxo_atualizado(db_session) is True
    assert not marca()


# ============================================================
# app/database.py
# ============================================================

def test_get_db_entrega_e_fecha_a_sessao():
    gerador = get_db()
    sessao = next(gerador)
    assert isinstance(sessao, type(SessionLocal()))
    gerador.close()  # dispara o finally que fecha a sessão


def test_init_db_cria_schema_e_admin_padrao():
    """init_db precisa ser seguro de rodar mais de uma vez."""
    init_db()
    init_db()

    db = SessionLocal()
    try:
        admins = db.query(UsuarioAdmin).filter(
            UsuarioAdmin.email == "admin@imunizacao.local"
        ).count()
    finally:
        db.close()
    assert admins == 1, "o admin padrão não pode ser duplicado a cada boot"


def test_ensure_default_admin_user_reaproveita_o_existente():
    primeiro = ensure_default_admin_user()
    segundo = ensure_default_admin_user()
    assert primeiro.email == segundo.email


# ============================================================
# RECÁLCULO DE STATUS NA EDIÇÃO (RF08)
# ============================================================

def _registro_para_editar(db_session, headers):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    return client.post(
        "/registros",
        headers=headers,
        json={
            "data_vacinacao": "2024-01-10",
            "municipio_vacina_id": "2304400",
            "municipio_residencia_id": "2303709",
            "idade": 30,
            "quantidade": 1,
        },
    ).json()["id"]


def test_editar_com_idade_invalida_marca_inconsistente(db_session):
    headers = auth_headers(db_session, email="edit-inc@example.com")
    registro_id = _registro_para_editar(db_session, headers)

    corpo = client.put(
        f"/registros/{registro_id}",
        headers=headers,
        json={
            "data_vacinacao": "2024-01-10",
            "municipio_vacina_id": "2304400",
            "municipio_residencia_id": "2303709",
            "idade": 200,
            "quantidade": 1,
        },
    ).json()

    assert corpo["status_dado"] == "DADO_INCONSISTENTE"


def test_editar_sem_residencia_marca_deslocamento_indeterminado(db_session):
    headers = auth_headers(db_session, email="edit-ind@example.com")
    registro_id = _registro_para_editar(db_session, headers)

    corpo = client.put(
        f"/registros/{registro_id}",
        headers=headers,
        json={
            "data_vacinacao": "2024-01-10",
            "municipio_vacina_id": "2304400",
            "municipio_residencia_id": None,
            "idade": 30,
            "quantidade": 1,
        },
    ).json()

    assert corpo["status_dado"] == "DESLOCAMENTO_INDETERMINADO"
    assert corpo["teve_deslocamento"] is None
