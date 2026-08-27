"""RF19 - Exportação das listagens filtradas em CSV (/exportacoes/*)."""

import csv
import io
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    AlertaCompletude,
    Municipio,
    RegistroVacinacao,
    UsuarioAdmin,
    Vacina,
)
from app.security import get_password_hash
from app.sql_views import marcar_fluxo_desatualizado

client = TestClient(app)


def _headers(db_session, role="ADMIN", email="export@example.com", municipio_id=None):
    db_session.add(
        UsuarioAdmin(
            email=email,
            senha_hash=get_password_hash("senha123"),
            role=role,
            municipio_alocado_id=municipio_id,
        )
    )
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": "senha123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ler_csv(response):
    """Devolve (cabeçalho, linhas) já sem o BOM que o Excel espera."""
    texto = response.content.decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    return linhas[0], linhas[1:]


def _setup_registros(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    covid = Vacina(nome="COVID-19", alta_complexidade=True)
    flu = Vacina(nome="Influenza")
    db_session.add_all([covid, flu])
    db_session.commit()
    db_session.refresh(covid)
    db_session.refresh(flu)

    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 15),
                idade=25,
                vacina_id=covid.id,
                municipio_residencia_id="2303709",
                municipio_vacina_id="2304400",
                teve_deslocamento=True,
                quantidade=2,
                status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2023, 6, 10),
                idade=70,
                vacina_id=flu.id,
                municipio_residencia_id="2304400",
                municipio_vacina_id="2304400",
                teve_deslocamento=False,
                quantidade=1,
                status_dado="VALIDO",
            ),
            # Inativo nunca é exportado (RN05).
            RegistroVacinacao(
                data_vacinacao=date(2024, 3, 1),
                vacina_id=covid.id,
                municipio_vacina_id="2304400",
                quantidade=99,
                ativo=False,
            ),
        ]
    )
    db_session.commit()
    return covid, flu


# ============================================================
# REGISTROS
# ============================================================


def test_exportar_registros_devolve_csv_com_cabecalho(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/registros", headers=headers)

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "attachment" in resposta.headers["content-disposition"]
    assert "registros.csv" in resposta.headers["content-disposition"]

    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == [
        "Data",
        "Município de aplicação",
        "Município de residência",
        "Vacina",
        "Idade",
        "Quantidade",
        "Houve deslocamento",
        "Status do dado",
    ]
    assert len(linhas) == 2
    assert linhas[0] == [
        "15/01/2024",
        "Fortaleza",
        "Caucaia",
        "COVID-19",
        "25",
        "2",
        "Sim",
        "Válido",
    ]


def test_exportar_registros_respeita_os_filtros_da_tela(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/registros",
        params={"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        headers=headers,
    )

    _, linhas = _ler_csv(resposta)
    assert [linha[0] for linha in linhas] == ["15/01/2024"]


def test_exportar_registros_exige_token(db_session):
    assert client.get("/exportacoes/registros").status_code == 401


def test_exportar_registros_corta_no_teto_e_sinaliza_truncamento(db_session, monkeypatch):
    from app.services import exportacao

    monkeypatch.setattr(exportacao, "LIMITE_LINHAS", 1)
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/registros", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"
    _, linhas = _ler_csv(resposta)
    assert len(linhas) == 1


def test_exportar_registros_sem_truncamento_sinaliza_false(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/registros", headers=headers)

    assert resposta.headers["x-export-truncated"] == "false"


def test_exportar_registros_sem_dados_devolve_apenas_o_cabecalho(db_session):
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/registros", headers=headers)

    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho[0] == "Data"
    assert linhas == []


def test_exportar_registros_preenche_travessao_para_campos_vazios(db_session):
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.commit()
    db_session.add(
        RegistroVacinacao(
            data_vacinacao=date(2024, 5, 4),
            municipio_vacina_id="2304400",
            quantidade=1,
            status_dado="DESLOCAMENTO_INDETERMINADO",
        )
    )
    db_session.commit()
    headers = _headers(db_session)

    _, linhas = _ler_csv(client.get("/exportacoes/registros", headers=headers))

    assert linhas[0] == [
        "04/05/2024",
        "Fortaleza",
        "—",
        "—",
        "—",
        "1",
        "—",
        "Deslocamento indeterminado",
    ]


# ============================================================
# MUNICÍPIOS E VACINAS
# ============================================================


def test_exportar_municipios_devolve_csv_com_cabecalho(db_session):
    db_session.add_all(
        [
            Municipio(
                id_ibge="2304400",
                nome="Fortaleza",
                uf="CE",
                regiao_saude="Região de Fortaleza",
                polo=True,
            ),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE", ativo=False),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/municipios", headers=headers)

    assert "municipios.csv" in resposta.headers["content-disposition"]
    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == [
        "Código IBGE",
        "Nome",
        "UF",
        "Região de saúde",
        "Município-polo",
        "Ativo",
    ]
    # Ordenado por nome, como na listagem.
    assert linhas == [
        ["2303709", "Caucaia", "CE", "—", "Não", "Não"],
        ["2304400", "Fortaleza", "CE", "Região de Fortaleza", "Sim", "Sim"],
    ]


def test_exportar_municipios_respeita_o_filtro_de_busca(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/municipios", params={"search": "cauc"}, headers=headers
    )

    _, linhas = _ler_csv(resposta)
    assert [linha[1] for linha in linhas] == ["Caucaia"]


def test_exportar_municipios_corta_no_teto(db_session, monkeypatch):
    from app.services import exportacao

    monkeypatch.setattr(exportacao, "LIMITE_LINHAS", 1)
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/municipios", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"
    _, linhas = _ler_csv(resposta)
    assert len(linhas) == 1


def test_exportar_municipios_exige_token(db_session):
    assert client.get("/exportacoes/municipios").status_code == 401


def test_exportar_vacinas_devolve_csv_com_cabecalho(db_session):
    db_session.add_all(
        [
            Vacina(nome="COVID-19", alta_complexidade=True),
            Vacina(nome="Influenza", ativo=False),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/vacinas", headers=headers)

    assert "vacinas.csv" in resposta.headers["content-disposition"]
    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == ["ID", "Nome", "Alta complexidade", "Ativo"]
    assert [linha[1:] for linha in linhas] == [
        ["COVID-19", "Sim", "Sim"],
        ["Influenza", "Não", "Não"],
    ]


def test_exportar_vacinas_respeita_o_filtro_de_alta_complexidade(db_session):
    db_session.add_all(
        [
            Vacina(nome="COVID-19", alta_complexidade=True),
            Vacina(nome="Influenza"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/vacinas", params={"alta_complexidade": "true"}, headers=headers
    )

    _, linhas = _ler_csv(resposta)
    assert [linha[1] for linha in linhas] == ["COVID-19"]


def test_exportar_vacinas_corta_no_teto(db_session, monkeypatch):
    from app.services import exportacao

    monkeypatch.setattr(exportacao, "LIMITE_LINHAS", 1)
    db_session.add_all([Vacina(nome="COVID-19"), Vacina(nome="Influenza")])
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/vacinas", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"


def test_exportar_vacinas_exige_token(db_session):
    assert client.get("/exportacoes/vacinas").status_code == 401


# ============================================================
# FLUXO INTERMUNICIPAL
# ============================================================


def _setup_fluxo(db_session):
    """Caucaia -> Fortaleza (3 doses em 2024) e Maracanaú -> Fortaleza (5 em 2023)."""
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
            Municipio(id_ibge="2308009", nome="Maracanaú", uf="CE"),
        ]
    )
    covid = Vacina(nome="COVID-19")
    db_session.add(covid)
    db_session.commit()
    db_session.refresh(covid)

    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 10),
                vacina_id=covid.id,
                municipio_residencia_id="2303709",
                municipio_vacina_id="2304400",
                teve_deslocamento=True,
                quantidade=3,
                status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2023, 2, 5),
                vacina_id=covid.id,
                municipio_residencia_id="2308009",
                municipio_vacina_id="2304400",
                teve_deslocamento=True,
                quantidade=5,
                status_dado="VALIDO",
            ),
        ]
    )
    db_session.commit()
    marcar_fluxo_desatualizado(db_session)
    db_session.commit()
    return covid


def test_exportar_fluxo_devolve_pares_ordenados_por_volume(db_session):
    _setup_fluxo(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/fluxo", headers=headers)

    assert "fluxo-intermunicipal.csv" in resposta.headers["content-disposition"]
    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == [
        "Município de origem (residência)",
        "Município de destino (aplicação)",
        "Doses",
    ]
    assert linhas == [
        ["Maracanaú", "Fortaleza", "5"],
        ["Caucaia", "Fortaleza", "3"],
    ]


def test_exportar_fluxo_respeita_o_filtro_de_periodo(db_session):
    _setup_fluxo(db_session)
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/fluxo",
        params={"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
        headers=headers,
    )

    _, linhas = _ler_csv(resposta)
    assert linhas == [["Caucaia", "Fortaleza", "3"]]


def test_exportar_fluxo_corta_no_teto(db_session, monkeypatch):
    from app.services import exportacao

    monkeypatch.setattr(exportacao, "LIMITE_LINHAS", 1)
    _setup_fluxo(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/fluxo", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"
    _, linhas = _ler_csv(resposta)
    assert len(linhas) == 1


def test_exportar_fluxo_exige_token(db_session):
    assert client.get("/exportacoes/fluxo").status_code == 401


# ============================================================
# ALERTAS DE COMPLETUDE
# ============================================================


def _setup_alertas(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    db_session.add_all(
        [
            AlertaCompletude(
                referencia_ano=2024,
                referencia_mes=3,
                municipio_id="2304400",
                total_observado=10,
                status="ABERTO",
            ),
            AlertaCompletude(
                referencia_ano=2023,
                referencia_mes=11,
                municipio_id="2303709",
                total_observado=4,
                status="RESOLVIDO",
            ),
        ]
    )
    db_session.commit()


def test_exportar_completude_devolve_csv_com_cabecalho(db_session):
    _setup_alertas(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/completude", headers=headers)

    assert "alertas-completude.csv" in resposta.headers["content-disposition"]
    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == [
        "Referência",
        "Município",
        "Total observado",
        "Status",
        "Criado em",
    ]
    assert [linha[:4] for linha in linhas] == [
        ["03/2024", "Fortaleza", "10", "Aberto"],
        ["11/2023", "Caucaia", "4", "Resolvido"],
    ]


def test_exportar_completude_respeita_o_filtro_de_status(db_session):
    _setup_alertas(db_session)
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/completude", params={"status": "RESOLVIDO"}, headers=headers
    )

    _, linhas = _ler_csv(resposta)
    assert [linha[1] for linha in linhas] == ["Caucaia"]


def test_exportar_completude_restringe_gestor_municipal_ao_seu_municipio(db_session):
    _setup_alertas(db_session)
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="gestor@example.com",
        municipio_id="2303709",
    )

    resposta = client.get("/exportacoes/completude", headers=headers)

    _, linhas = _ler_csv(resposta)
    assert [linha[1] for linha in linhas] == ["Caucaia"]


def test_exportar_completude_corta_no_teto(db_session, monkeypatch):
    from app.services import exportacao

    monkeypatch.setattr(exportacao, "LIMITE_LINHAS", 1)
    _setup_alertas(db_session)
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/completude", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"


def test_exportar_completude_exige_token(db_session):
    assert client.get("/exportacoes/completude").status_code == 401


# ============================================================
# ALTA COMPLEXIDADE
# ============================================================


def test_exportar_alta_complexidade_traz_uma_linha_por_municipio(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    vacina = Vacina(nome="Imunoglobulina", alta_complexidade=True)
    db_session.add(vacina)
    db_session.commit()
    db_session.refresh(vacina)
    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 10),
                vacina_id=vacina.id,
                municipio_residencia_id="2303709",
                municipio_vacina_id="2304400",
                teve_deslocamento=True,
                quantidade=3,
                status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2024, 2, 10),
                vacina_id=vacina.id,
                municipio_residencia_id="2303709",
                municipio_vacina_id="2303709",
                teve_deslocamento=False,
                quantidade=1,
                status_dado="VALIDO",
            ),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/exportacoes/alta-complexidade", headers=headers)

    assert "alta-complexidade.csv" in resposta.headers["content-disposition"]
    cabecalho, linhas = _ler_csv(resposta)
    assert cabecalho == [
        "Vacina",
        "Total de doses",
        "Doses deslocadas",
        "Doses de origem indeterminada",
        "Taxa de deslocamento (%)",
        "Centro de referência",
        "Município de aplicação",
        "Doses no município",
        "% do total da vacina",
    ]
    assert linhas == [
        [
            "Imunoglobulina", "4", "3", "0", "75,0", "Fortaleza",
            "Fortaleza", "3", "75,0",
        ],
        [
            "Imunoglobulina", "4", "3", "0", "75,0", "Fortaleza",
            "Caucaia", "1", "25,0",
        ],
    ]


def test_exportar_alta_complexidade_mostra_vacina_sem_registro(db_session):
    db_session.add(Vacina(nome="Imunoglobulina", alta_complexidade=True))
    db_session.commit()
    headers = _headers(db_session)

    _, linhas = _ler_csv(client.get("/exportacoes/alta-complexidade", headers=headers))

    assert linhas == [
        ["Imunoglobulina", "0", "0", "0", "0,0", "—", "—", "—", "—"]
    ]


def test_exportar_alta_complexidade_sem_vacinas_devolve_so_o_cabecalho(db_session):
    headers = _headers(db_session)

    cabecalho, linhas = _ler_csv(
        client.get("/exportacoes/alta-complexidade", headers=headers)
    )

    assert cabecalho[0] == "Vacina"
    assert linhas == []


def test_exportar_alta_complexidade_respeita_o_top_municipios(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    vacina = Vacina(nome="Imunoglobulina", alta_complexidade=True)
    db_session.add(vacina)
    db_session.commit()
    db_session.refresh(vacina)
    db_session.add_all(
        [
            RegistroVacinacao(
                data_vacinacao=date(2024, 1, 10),
                vacina_id=vacina.id,
                municipio_vacina_id="2304400",
                quantidade=3,
                status_dado="VALIDO",
            ),
            RegistroVacinacao(
                data_vacinacao=date(2024, 2, 10),
                vacina_id=vacina.id,
                municipio_vacina_id="2303709",
                quantidade=1,
                status_dado="VALIDO",
            ),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get(
        "/exportacoes/alta-complexidade", params={"top_municipios": 1}, headers=headers
    )

    _, linhas = _ler_csv(resposta)
    assert [linha[6] for linha in linhas] == ["Fortaleza"]


def test_exportar_alta_complexidade_exige_token(db_session):
    assert client.get("/exportacoes/alta-complexidade").status_code == 401
