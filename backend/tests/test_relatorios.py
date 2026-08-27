"""RF20 - Relatório consolidado em PDF de cada painel (/relatorios/*)."""

import io
from datetime import date

from fastapi.testclient import TestClient
from pypdf import PdfReader

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


def _headers(db_session, role="ADMIN", email="relatorio@example.com", municipio_id=None):
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


def _texto(response) -> str:
    """Texto de todas as páginas do PDF, com as quebras de linha achatadas."""
    leitor = PdfReader(io.BytesIO(response.content))
    return " ".join(pagina.extract_text() for pagina in leitor.pages).replace("\n", " ")


def _setup_registros(db_session):
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
        ]
    )
    db_session.commit()
    return covid, flu


# ============================================================
# REGISTROS
# ============================================================


def test_relatorio_de_registros_e_um_pdf_para_download(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get("/relatorios/registros", headers=headers)

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/pdf")
    assert "attachment" in resposta.headers["content-disposition"]
    assert "registros.pdf" in resposta.headers["content-disposition"]
    assert resposta.content.startswith(b"%PDF-")


def test_relatorio_traz_cabecalho_de_prestacao_de_contas(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/registros", headers=headers))

    assert "Caminhos da Imunização" in texto
    assert "Registros de vacinação" in texto
    # Quem emitiu e quando: é o que dá rastreabilidade ao documento oficial.
    assert "relatorio@example.com" in texto
    assert "Emitido em" in texto


def test_relatorio_lista_os_filtros_aplicados(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
            headers=headers,
        )
    )

    assert "Filtros aplicados" in texto
    assert "01/01/2024" in texto
    assert "31/12/2024" in texto


def test_relatorio_diz_quando_um_filtro_nao_foi_usado(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/registros", headers=headers))

    assert "Todos" in texto


def test_relatorio_de_registros_traz_a_tabela_do_recorte(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/registros", headers=headers))

    assert "Município de aplicação" in texto
    assert "15/01/2024" in texto
    assert "Fortaleza" in texto
    assert "COVID-19" in texto


def test_relatorio_de_registros_respeita_os_filtros_da_tela(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
            headers=headers,
        )
    )

    assert "15/01/2024" in texto
    assert "10/06/2023" not in texto


def test_relatorio_sem_dados_informa_o_recorte_vazio(db_session):
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/registros", headers=headers))

    assert "Nenhum registro encontrado para os filtros aplicados." in texto


def test_relatorio_corta_no_teto_e_avisa_no_documento(db_session, monkeypatch):
    from app.services import relatorio_pdf

    monkeypatch.setattr(relatorio_pdf, "LIMITE_LINHAS", 1)
    _setup_registros(db_session)
    headers = _headers(db_session)

    resposta = client.get("/relatorios/registros", headers=headers)
    texto = _texto(resposta)

    assert resposta.headers["x-export-truncated"] == "true"
    assert "Exibindo as primeiras 1 de 2 linhas" in texto


def test_relatorio_de_registros_exige_token(db_session):
    assert client.get("/relatorios/registros").status_code == 401


# ============================================================
# MUNICÍPIOS E VACINAS
# ============================================================


def test_relatorio_de_municipios_traz_cabecalho_filtros_e_tabela(db_session):
    db_session.add_all(
        [
            Municipio(
                id_ibge="2304400",
                nome="Fortaleza",
                uf="CE",
                regiao_saude="Região de Fortaleza",
                polo=True,
            ),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/relatorios/municipios", headers=headers)
    texto = _texto(resposta)

    assert "municipios.pdf" in resposta.headers["content-disposition"]
    assert "Municípios cadastrados" in texto
    assert "Código IBGE" in texto
    assert "Região de Fortaleza" in texto
    assert "Caucaia" in texto


def test_relatorio_de_municipios_respeita_o_filtro_de_busca(db_session):
    db_session.add_all(
        [
            Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"),
            Municipio(id_ibge="2303709", nome="Caucaia", uf="CE"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    texto = _texto(
        client.get("/relatorios/municipios", params={"search": "cauc"}, headers=headers)
    )

    assert "Caucaia" in texto
    assert "Fortaleza" not in texto


def test_relatorio_de_municipios_exige_token(db_session):
    assert client.get("/relatorios/municipios").status_code == 401


def test_relatorio_de_vacinas_traz_a_tabela_do_recorte(db_session):
    db_session.add_all(
        [
            Vacina(nome="Imunoglobulina", alta_complexidade=True),
            Vacina(nome="Influenza", ativo=False),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/relatorios/vacinas", headers=headers)
    texto = _texto(resposta)

    assert "vacinas.pdf" in resposta.headers["content-disposition"]
    assert "Vacinas cadastradas" in texto
    assert "Alta complexidade" in texto
    assert "Imunoglobulina" in texto


def test_relatorio_de_vacinas_respeita_o_filtro_de_alta_complexidade(db_session):
    db_session.add_all(
        [
            Vacina(nome="Imunoglobulina", alta_complexidade=True),
            Vacina(nome="Influenza"),
        ]
    )
    db_session.commit()
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/vacinas", params={"alta_complexidade": "true"}, headers=headers
        )
    )

    assert "Imunoglobulina" in texto
    assert "Influenza" not in texto


def test_relatorio_de_vacinas_corta_no_teto(db_session, monkeypatch):
    from app.services import relatorio_pdf

    monkeypatch.setattr(relatorio_pdf, "LIMITE_LINHAS", 1)
    db_session.add_all([Vacina(nome="Imunoglobulina"), Vacina(nome="Influenza")])
    db_session.commit()
    headers = _headers(db_session)

    resposta = client.get("/relatorios/vacinas", headers=headers)

    assert resposta.headers["x-export-truncated"] == "true"
    assert "Exibindo as primeiras 1 de 2 linhas" in _texto(resposta)


def test_relatorio_de_vacinas_exige_token(db_session):
    assert client.get("/relatorios/vacinas").status_code == 401


# ============================================================
# FLUXO INTERMUNICIPAL
# ============================================================


def _setup_fluxo(db_session):
    """Caucaia para Fortaleza (3 doses em 2024) e Maracanaú para Fortaleza (5 em 2023)."""
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


def test_relatorio_de_fluxo_traz_grafico_e_tabela(db_session):
    _setup_fluxo(db_session)
    headers = _headers(db_session)

    resposta = client.get("/relatorios/fluxo", headers=headers)
    texto = _texto(resposta)

    assert "fluxo-intermunicipal.pdf" in resposta.headers["content-disposition"]
    assert "Fluxo intermunicipal" in texto
    assert "Maiores fluxos do recorte" in texto
    assert "Município de origem (residência)" in texto
    assert "Maracanaú" in texto


def test_relatorio_de_fluxo_respeita_o_filtro_de_periodo(db_session):
    _setup_fluxo(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/fluxo",
            params={"data_inicio": "2024-01-01", "data_fim": "2024-12-31"},
            headers=headers,
        )
    )

    assert "Caucaia" in texto
    assert "Maracanaú" not in texto


def test_relatorio_de_fluxo_sem_deslocamento_nao_quebra(db_session):
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/fluxo", headers=headers))

    assert "Nenhum deslocamento encontrado para os filtros aplicados." in texto


def test_relatorio_de_fluxo_exige_token(db_session):
    assert client.get("/relatorios/fluxo").status_code == 401


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


def test_relatorio_de_completude_traz_grafico_e_tabela(db_session):
    _setup_alertas(db_session)
    headers = _headers(db_session)

    resposta = client.get("/relatorios/completude", headers=headers)
    texto = _texto(resposta)

    assert "alertas-completude.pdf" in resposta.headers["content-disposition"]
    assert "Alertas de completude" in texto
    assert "Alertas por status" in texto
    assert "Referência" in texto
    assert "03/2024" in texto


def test_relatorio_de_completude_respeita_o_filtro_de_status(db_session):
    _setup_alertas(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/completude", params={"status": "RESOLVIDO"}, headers=headers
        )
    )

    assert "Caucaia" in texto
    assert "Fortaleza" not in texto


def test_relatorio_de_completude_restringe_gestor_municipal(db_session):
    _setup_alertas(db_session)
    headers = _headers(
        db_session,
        role="GESTOR_MUNICIPAL",
        email="gestor.pdf@example.com",
        municipio_id="2303709",
    )

    texto = _texto(client.get("/relatorios/completude", headers=headers))

    assert "Caucaia" in texto
    assert "Fortaleza" not in texto


def test_relatorio_de_completude_exige_token(db_session):
    assert client.get("/relatorios/completude").status_code == 401


# ============================================================
# ALTA COMPLEXIDADE
# ============================================================


def _setup_alta_complexidade(db_session, com_deslocamento=True):
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
                municipio_residencia_id="2303709" if com_deslocamento else None,
                municipio_vacina_id="2304400",
                teve_deslocamento=com_deslocamento,
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
    return vacina


def test_relatorio_de_alta_complexidade_traz_grafico_e_tabela(db_session):
    _setup_alta_complexidade(db_session)
    headers = _headers(db_session)

    resposta = client.get("/relatorios/alta-complexidade", headers=headers)
    texto = _texto(resposta)

    assert "alta-complexidade.pdf" in resposta.headers["content-disposition"]
    assert "Imunobiológicos de alta complexidade" in texto
    assert "Doses por vacina" in texto
    assert "Taxa de deslocamento (%)" in texto
    assert "Imunoglobulina" in texto


def test_relatorio_de_alta_complexidade_sem_vacinas_marcadas(db_session):
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/alta-complexidade", headers=headers))

    assert "Nenhuma vacina de alta complexidade encontrada." in texto


def test_relatorio_de_alta_complexidade_respeita_o_top_municipios(db_session):
    _setup_alta_complexidade(db_session, com_deslocamento=False)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/alta-complexidade",
            params={"top_municipios": 1},
            headers=headers,
        )
    )

    assert "Fortaleza" in texto
    assert "Caucaia" not in texto


def test_relatorio_de_alta_complexidade_exige_token(db_session):
    assert client.get("/relatorios/alta-complexidade").status_code == 401


# ============================================================
# COMO O DOCUMENTO DESCREVE O RECORTE
# ============================================================


def test_relatorio_descreve_periodo_aberto_no_fim(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"data_inicio": "2024-01-01"},
            headers=headers,
        )
    )

    assert "a partir de 01/01/2024" in texto


def test_relatorio_descreve_periodo_aberto_no_inicio(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros", params={"data_fim": "2024-12-31"}, headers=headers
        )
    )

    assert "até 31/12/2024" in texto


def test_relatorio_descreve_faixa_etaria_fechada(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"idade_min": 18, "idade_max": 60},
            headers=headers,
        )
    )

    assert "18 a 60 anos" in texto


def test_relatorio_descreve_faixa_etaria_so_com_minimo(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get("/relatorios/registros", params={"idade_min": 18}, headers=headers)
    )

    assert "a partir de 18 anos" in texto


def test_relatorio_descreve_faixa_etaria_so_com_maximo(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get("/relatorios/registros", params={"idade_max": 60}, headers=headers)
    )

    assert "até 60 anos" in texto


def test_relatorio_nomeia_o_municipio_e_a_vacina_do_filtro(db_session):
    covid, _ = _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"municipio_id": "2304400", "vacina_id": covid.id},
            headers=headers,
        )
    )

    # O código IBGE sozinho não diz nada a quem lê a prestação de contas.
    assert "Fortaleza (2304400)" in texto
    assert "COVID-19" in texto


def test_relatorio_cai_no_codigo_quando_o_filtro_aponta_para_algo_inexistente(db_session):
    _setup_registros(db_session)
    headers = _headers(db_session)

    texto = _texto(
        client.get(
            "/relatorios/registros",
            params={"municipio_id": "9999999", "vacina_id": 4242},
            headers=headers,
        )
    )

    assert "9999999" in texto
    assert "4242" in texto


def test_relatorio_de_municipios_descreve_a_situacao_filtrada(db_session):
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.commit()
    headers = _headers(db_session)

    ativos = _texto(
        client.get("/relatorios/municipios", params={"ativo": "true"}, headers=headers)
    )
    inativos = _texto(
        client.get("/relatorios/municipios", params={"ativo": "false"}, headers=headers)
    )

    assert "Somente ativos" in ativos
    assert "Somente inativos" in inativos


def test_relatorio_de_municipios_registra_a_uf_filtrada(db_session):
    db_session.add(Municipio(id_ibge="2304400", nome="Fortaleza", uf="CE"))
    db_session.commit()
    headers = _headers(db_session)

    texto = _texto(
        client.get("/relatorios/municipios", params={"uf": "ce"}, headers=headers)
    )

    assert "CE" in texto


def test_relatorio_de_vacinas_descreve_a_complexidade_filtrada(db_session):
    db_session.add(Vacina(nome="Influenza"))
    db_session.commit()
    headers = _headers(db_session)

    padrao = _texto(
        client.get(
            "/relatorios/vacinas", params={"alta_complexidade": "false"}, headers=headers
        )
    )

    assert "Somente padrão" in padrao


def test_relatorio_de_alta_complexidade_mostra_vacina_sem_nenhuma_aplicacao(db_session):
    db_session.add(Vacina(nome="Imunoglobulina", alta_complexidade=True))
    db_session.commit()
    headers = _headers(db_session)

    texto = _texto(client.get("/relatorios/alta-complexidade", headers=headers))

    # Esconder a vacina zerada tiraria da vista justamente o caso a investigar.
    assert "Imunoglobulina" in texto
    assert "Doses por vacina" in texto
