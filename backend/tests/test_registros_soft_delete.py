from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Base, LogAuditoria, Municipio, RegistroVacinacao, UsuarioAdmin
from app.routers.registros import excluir_registro, listar_registros


@pytest.fixture
def isolated_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _criar_cenario(db):
    usuario = UsuarioAdmin(
        email="soft-delete@example.com",
        senha_hash="hash",
        role="ADMIN",
    )
    municipio = Municipio(
        id_ibge="2304400",
        nome="Fortaleza",
        uf="CE",
    )
    registro = RegistroVacinacao(
        data_vacinacao=date(2026, 8, 14),
        idade=30,
        vacina_id=None,
        municipio_residencia_id="2304400",
        municipio_vacina_id="2304400",
        teve_deslocamento=False,
        quantidade=1,
        status_dado="VALIDO",
    )

    db.add_all([usuario, municipio, registro])
    db.commit()
    db.refresh(usuario)
    db.refresh(registro)

    return usuario, registro


def test_rota_delete_esta_registrada():
    assert any(
        route.path == "/registros/{id}" and "DELETE" in getattr(route, "methods", set())
        for route in app.routes
    )


def test_delete_realiza_exclusao_logica_e_gera_auditoria(isolated_db):
    usuario, registro = _criar_cenario(isolated_db)
    registro_id = registro.id

    resultado = excluir_registro(
        id=registro_id,
        db=isolated_db,
        current_user=usuario,
    )

    assert resultado is None

    isolated_db.expire_all()

    registro_persistido = (
        isolated_db.query(RegistroVacinacao)
        .filter(RegistroVacinacao.id == registro_id)
        .one()
    )

    # O registro continua fisicamente no banco, porém inativo.
    assert registro_persistido.ativo is False
    assert isolated_db.query(RegistroVacinacao).filter(RegistroVacinacao.id == registro_id).count() == 1

    log = (
        isolated_db.query(LogAuditoria)
        .filter(LogAuditoria.registro_id == registro_id)
        .one()
    )

    assert log.tabela == "registros_vacinacao"
    assert log.acao == "DELETE"
    assert log.usuario_id == usuario.id
    assert log.valores_antigos["ativo"] is True
    assert log.valores_novos["ativo"] is False

    # A listagem padrão não deve exibir o registro inativo.
    pagina = listar_registros(
        municipio_id=None,
        vacina_id=None,
        data_inicio=None,
        data_fim=None,
        idade_min=None,
        idade_max=None,
        status_dado=None,
        page=1,
        page_size=10,
        db=isolated_db,
        current_user=usuario,
    )

    assert pagina.total == 0
    assert pagina.items == []


def test_delete_de_registro_inexistente_retorna_404(isolated_db):
    usuario, registro = _criar_cenario(isolated_db)

    excluir_registro(
        id=registro.id,
        db=isolated_db,
        current_user=usuario,
    )

    with pytest.raises(HTTPException) as exc:
        excluir_registro(
            id=registro.id,
            db=isolated_db,
            current_user=usuario,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Registro de vacinação não encontrado."
