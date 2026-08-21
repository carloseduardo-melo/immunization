"""RF18 - Cobre o painel de imunobiológicos de alta complexidade."""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Municipio, RegistroVacinacao, UsuarioAdmin, Vacina
from app.security import get_password_hash

client = TestClient(app)


def auth_headers(db_session, email="altacomplexidade@example.com", role="ADMIN"):
    db_session.add(
        UsuarioAdmin(email=email, senha_hash=get_password_hash("senha123"), role=role)
    )
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _registro(vacina_id, municipio, quantidade, deslocou=False, status="VALIDO", ativo=True):
    return RegistroVacinacao(
        data_vacinacao=date(2024, 5, 10),
        vacina_id=vacina_id,
        municipio_vacina_id=municipio,
        teve_deslocamento=deslocou,
        quantidade=quantidade,
        status_dado=status,
        ativo=ativo,
    )


def setup_dados(db_session):
    """Imunoglobulina: 200 doses / 130 deslocadas. Raiva: 50 / 40.
    Palivizumabe: nenhum registro. COVID e Antiga não devem aparecer."""
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
            Municipio(id_ibge="2312908", nome="Sobral", uf="CE"),
        ]
    )
    imuno = Vacina(nome="Imunoglobulina", alta_complexidade=True)
    raiva = Vacina(nome="Raiva humana", alta_complexidade=True)
    palivizumabe = Vacina(nome="Palivizumabe", alta_complexidade=True)
    covid = Vacina(nome="COVID-19", alta_complexidade=False)
    antiga = Vacina(nome="Antiga", alta_complexidade=True, ativo=False)
    db_session.add_all([imuno, raiva, palivizumabe, covid, antiga])
    db_session.commit()
    for vacina in (imuno, raiva, palivizumabe, covid, antiga):
        db_session.refresh(vacina)

    db_session.add_all(
        [
            _registro(imuno.id, "2304400", 100, deslocou=True),
            _registro(imuno.id, "2304400", 50),
            _registro(imuno.id, "2312908", 30, deslocou=True),
            _registro(imuno.id, "2303709", 20),
            _registro(imuno.id, "2304400", 999, status="DADO_INCONSISTENTE"),
            _registro(imuno.id, "2304400", 888, ativo=False),
            _registro(raiva.id, "2312908", 40, deslocou=True),
            _registro(raiva.id, "2304400", 10),
            _registro(covid.id, "2304400", 500),
            _registro(antiga.id, "2304400", 70),
        ]
    )
    db_session.commit()
    return imuno, raiva, palivizumabe


def test_sem_token_retorna_401():
    assert client.get("/alta-complexidade").status_code == 401


def test_lista_apenas_vacinas_de_alta_complexidade_ativas(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    corpo = client.get("/alta-complexidade", headers=headers).json()
    nomes = [item["vacina_nome"] for item in corpo["items"]]

    assert nomes == ["Imunoglobulina", "Raiva humana", "Palivizumabe"], (
        "ordenadas por volume desc; COVID-19 não é alta complexidade e Antiga está inativa"
    )
    assert corpo["total_vacinas"] == 3


def test_taxa_de_deslocamento_ignora_inconsistente_e_inativo(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get("/alta-complexidade", headers=headers).json()["items"]
    imuno = itens[0]

    assert imuno["total_doses"] == 200, "100 + 50 + 30 + 20"
    assert imuno["total_deslocamentos"] == 130, "100 + 30"
    assert imuno["taxa_deslocamento"] == 65.0


def test_centro_de_referencia_e_o_municipio_de_maior_volume(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get("/alta-complexidade", headers=headers).json()["items"]
    imuno = itens[0]

    assert imuno["centro_referencia_id"] == "2304400"
    assert imuno["centro_referencia_nome"] == "Fortaleza"
    assert [m["municipio_nome"] for m in imuno["municipios"]] == [
        "Fortaleza", "Sobral", "Caucaia",
    ]
    assert imuno["municipios"][0]["total_doses"] == 150
    assert imuno["municipios"][0]["percentual"] == 75.0
    assert imuno["municipios"][1]["percentual"] == 15.0


def test_top_municipios_corta_a_lista(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get(
        "/alta-complexidade", params={"top_municipios": 2}, headers=headers
    ).json()["items"]

    assert len(itens[0]["municipios"]) == 2
    assert itens[0]["centro_referencia_nome"] == "Fortaleza"


def test_top_municipios_invalido_volta_ao_padrao(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get(
        "/alta-complexidade", params={"top_municipios": 0}, headers=headers
    ).json()["items"]

    assert len(itens[0]["municipios"]) == 3, "padrão de 3 municípios"


def test_top_municipios_acima_do_teto_e_limitado(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    resposta = client.get(
        "/alta-complexidade", params={"top_municipios": 500}, headers=headers
    )

    assert resposta.status_code == 200
    assert len(resposta.json()["items"][0]["municipios"]) == 3, "só há 3 municípios"


def test_vacina_sem_registro_aparece_zerada(db_session):
    setup_dados(db_session)
    headers = auth_headers(db_session)

    itens = client.get("/alta-complexidade", headers=headers).json()["items"]
    palivizumabe = itens[-1]

    assert palivizumabe["vacina_nome"] == "Palivizumabe"
    assert palivizumabe["total_doses"] == 0
    assert palivizumabe["total_deslocamentos"] == 0
    assert palivizumabe["taxa_deslocamento"] == 0.0
    assert palivizumabe["municipios"] == []
    assert palivizumabe["centro_referencia_id"] is None
    assert palivizumabe["centro_referencia_nome"] is None


def test_sem_vacinas_de_alta_complexidade_devolve_lista_vazia(db_session):
    headers = auth_headers(db_session)

    corpo = client.get("/alta-complexidade", headers=headers).json()

    assert corpo["items"] == []
    assert corpo["total_vacinas"] == 0


def test_desempate_de_vacinas_e_de_municipios_e_deterministico(db_session):
    """Duas vacinas empatadas em total_doses (100) e, dentro de uma delas, dois
    municípios empatados em doses (50) - os dois cortes precisam de uma chave
    secundária ou o resultado muda de execução para execução sem o dado mudar."""
    db_session.add_all(
        [
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
        ]
    )
    zilfovir = Vacina(nome="Zilfovir", alta_complexidade=True)
    anfotericina = Vacina(nome="Anfotericina", alta_complexidade=True)
    db_session.add_all([zilfovir, anfotericina])
    db_session.commit()
    db_session.refresh(zilfovir)
    db_session.refresh(anfotericina)

    db_session.add_all(
        [
            # Zilfovir: 2304400 e 2303709 empatados em 50 doses cada.
            _registro(zilfovir.id, "2304400", 50),
            _registro(zilfovir.id, "2303709", 50),
            # Anfotericina: mesmo total_doses (100) de Zilfovir.
            _registro(anfotericina.id, "2304400", 100),
        ]
    )
    db_session.commit()
    headers = auth_headers(db_session)

    itens = client.get("/alta-complexidade", headers=headers).json()["items"]

    assert [item["vacina_nome"] for item in itens] == ["Anfotericina", "Zilfovir"], (
        "empate em total_doses (100) resolvido em ordem alfabética de vacina_nome"
    )

    zilfovir_item = itens[1]
    assert zilfovir_item["municipios"][0]["municipio_id"] == "2303709", (
        "empate de 50 doses entre municípios resolvido pelo menor "
        "municipio_vacina_id (2303709 < 2304400)"
    )
    assert zilfovir_item["centro_referencia_id"] == "2303709"


def test_total_indeterminado_reduz_o_denominador_da_taxa(db_session):
    """Registros sem município de residência (teve_deslocamento NULL) contam em
    total_doses mas ficam fora do numerador e do denominador de
    taxa_deslocamento - senão a taxa fica diluída de forma desigual."""
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    vacina = Vacina(nome="Imunoglobulina Antitetânica", alta_complexidade=True)
    db_session.add(vacina)
    db_session.commit()
    db_session.refresh(vacina)

    db_session.add_all(
        [
            _registro(vacina.id, "2304400", 60, deslocou=True),
            _registro(vacina.id, "2304400", 20, deslocou=False),
            _registro(
                vacina.id, "2304400", 20, deslocou=None,
                status="DESLOCAMENTO_INDETERMINADO",
            ),
        ]
    )
    db_session.commit()
    headers = auth_headers(db_session)

    item = client.get("/alta-complexidade", headers=headers).json()["items"][0]

    assert item["total_doses"] == 100, "60 + 20 + 20 - a origem indeterminada conta aqui"
    assert item["total_deslocamentos"] == 60
    assert item["total_indeterminado"] == 20
    assert item["taxa_deslocamento"] == 75.0, (
        "60 / (100 - 20) * 100 = 75.0 - denominador exclui a origem indeterminada"
    )
