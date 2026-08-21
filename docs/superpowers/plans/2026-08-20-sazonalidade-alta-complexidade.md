# RF17 (Sazonalidade) e RF18 (Alta Complexidade) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar dois painéis analíticos novos — sazonalidade mensal da vacinação (RF17) e imunobiológicos de alta complexidade com seus centros de referência (RF18) — cada um com endpoint próprio no backend, tela própria no frontend e item próprio na navegação lateral.

**Architecture:** Um router FastAPI e um módulo de UI Streamlit por RF, seguindo o padrão já estabelecido por `fluxo` e `completude`. Os dois endpoints agregam direto em `registros_vacinacao` com `func.extract`/`func.sum` (mesma técnica de `dashboard.py`, que roda igual em PostgreSQL e SQLite), são somente leitura, autenticados por `get_current_user` e sem restrição por município. O frontend consome via `api_client.py` (HTTP puro) e `data_cache.py` (memoização com `st.cache_data`).

**Tech Stack:** FastAPI 0.111, SQLAlchemy 2.0.36, Pydantic 2.11, pytest 7.4 + TestClient; Streamlit 1.36, pandas 2.2.2, `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-08-20-sazonalidade-alta-complexidade-design.md`

## Global Constraints

- Cobertura de testes: `backend/pytest.ini` e `frontend/pytest.ini` usam `--cov-fail-under=100` com `branch = True`. **Todo ramo novo precisa de teste**, inclusive cada `except ApiError` e cada `if` de filtro.
- Backend roda a suíte a partir da raiz do repositório (`pytest`, config em `pytest.ini`, `pythonpath = backend`). Frontend roda a partir de `frontend/` (`pytest`, `pythonpath = .`).
- Banco de teste é SQLite (`test.db`); nada de SQL específico de PostgreSQL (`date_trunc`, `stddev`, window functions) nos endpoints novos.
- Commits **sem** trailer `Co-Authored-By` (preferência do repositório).
- Nenhuma migração Alembic: os dois painéis usam apenas tabelas e colunas existentes.
- Mensagens de UI e docstrings em português, como no restante do projeto.
- Base de cálculo do RF18: `ativo = true` e `status_dado != 'DADO_INCONSISTENTE'`, no numerador **e** no denominador. Difere do `taxa_mobilidade` de `/dashboard/resumo`, que usa base mista (denominador com inconsistentes, numerador sem) — a taxa do RF18 pode divergir da do Dashboard para a mesma vacina, por decisão de projeto. `/dashboard/resumo` não deve ser alterado.

---

### Task 1: Backend RF17 — endpoint `GET /sazonalidade`

**Files:**
- Modify: `backend/app/schemas.py` (acrescentar ao final)
- Create: `backend/app/routers/sazonalidade.py`
- Modify: `backend/app/main.py` (import, `OPENAPI_TAGS`, `include_router`)
- Test: `backend/tests/test_sazonalidade.py`

**Interfaces:**
- Consumes: `app.database.get_db`, `app.dependencies.get_current_user`, `app.models.RegistroVacinacao`.
- Produces: `GET /sazonalidade` com query params `vacina_id: int | None`, `municipio_id: str | None`, `ano_inicio: int | None`, `ano_fim: int | None`; resposta `SazonalidadeResponse` = `{"kpis": {...}, "meses": [12 itens]}`. Schemas `SazonalidadeMes`, `SazonalidadeKPIs`, `SazonalidadeResponse` exportados de `app.schemas`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/test_sazonalidade.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run (na raiz do repositório): `pytest backend/tests/test_sazonalidade.py -v --no-cov`
Expected: FAIL — todas as chamadas devolvem 404, porque `/sazonalidade` ainda não existe.

- [ ] **Step 3: Acrescentar os schemas**

Ao final de `backend/app/schemas.py`:

```python


# ==========================================
# SAZONALIDADE (RF17)
# ==========================================


class SazonalidadeMes(BaseModel):
    mes: int
    nome_mes: str
    total_doses: int
    indice_sazonalidade: float


class SazonalidadeKPIs(BaseModel):
    total_periodo: int
    media_mensal: float
    mes_pico: Optional[int] = None
    mes_pico_nome: Optional[str] = None
    mes_vale: Optional[int] = None
    mes_vale_nome: Optional[str] = None
    amplitude: float


class SazonalidadeResponse(BaseModel):
    kpis: SazonalidadeKPIs
    meses: list[SazonalidadeMes]
```

- [ ] **Step 4: Criar o router**

Criar `backend/app/routers/sazonalidade.py`:

```python
"""RF17 - Painel de sazonalidade: volume de vacinação por mês do ano.

As doze barras consolidam todos os anos do recorte (Jan..Dez). A série
cronológica ano-a-mês já existe em `/dashboard/resumo`; aqui a pergunta é outra:
"em qual mês do ano concentrar a campanha".

A agregação usa `func.extract`, que o SQLAlchemy traduz tanto para PostgreSQL
(produção) quanto para SQLite (dev.db/test.db) - o mesmo cuidado já tomado em
dashboard.py.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegistroVacinacao
from app.schemas import SazonalidadeKPIs, SazonalidadeMes, SazonalidadeResponse

router = APIRouter(prefix="/sazonalidade", tags=["Sazonalidade"])

NOMES_MESES = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


@router.get(
    "",
    response_model=SazonalidadeResponse,
    summary="Volume de vacinação por mês do ano",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_sazonalidade(
    vacina_id: Optional[int] = None,
    municipio_id: Optional[str] = None,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF17 - Retorna o total de doses de cada mês do ano (1 a 12), o índice de
    sazonalidade de cada mês (total do mês dividido pela média mensal) e os KPIs
    de pico, vale e amplitude.

    Considera todos os `status_dado`: o mês vem de `data_vacinacao`, que é
    obrigatória e não é afetada pelas inconsistências de idade ou deslocamento -
    completude de volume não é validade do dado. Registros inativos ficam de
    fora. `municipio_id` filtra pelo município de aplicação, como no Dashboard.
    """
    query = db.query(RegistroVacinacao).filter(RegistroVacinacao.ativo == True)

    if vacina_id:
        query = query.filter(RegistroVacinacao.vacina_id == vacina_id)
    if municipio_id:
        query = query.filter(RegistroVacinacao.municipio_vacina_id == municipio_id)

    ano_col = func.extract("year", RegistroVacinacao.data_vacinacao)
    if ano_inicio:
        query = query.filter(ano_col >= ano_inicio)
    if ano_fim:
        query = query.filter(ano_col <= ano_fim)

    mes_col = func.extract("month", RegistroVacinacao.data_vacinacao).label("mes")
    linhas = (
        query.with_entities(
            mes_col, func.sum(RegistroVacinacao.quantidade).label("total")
        )
        .group_by(mes_col)
        .all()
    )
    totais = {int(linha.mes): int(linha.total) for linha in linhas}

    total_periodo = sum(totais.values())
    # Divisor fixo em 12 (e não "meses com dado"): assim o índice de um mês
    # zerado é 0,0 e a soma dos doze índices é sempre 12, independente de
    # quantos meses têm registro.
    media_mensal = total_periodo / 12

    meses = [
        SazonalidadeMes(
            mes=numero,
            nome_mes=NOMES_MESES[numero - 1],
            total_doses=totais.get(numero, 0),
            indice_sazonalidade=(
                round(totais.get(numero, 0) / media_mensal, 2) if media_mensal else 0.0
            ),
        )
        for numero in range(1, 13)
    ]

    kpis = SazonalidadeKPIs(
        total_periodo=total_periodo,
        media_mensal=round(media_mensal, 2),
        amplitude=0.0,
    )

    if total_periodo:
        # Empate resolvido pelo menor número de mês, nos dois extremos, para a
        # resposta ser determinística.
        pico = max(meses, key=lambda mes: (mes.total_doses, -mes.mes))
        vale = min(meses, key=lambda mes: (mes.total_doses, mes.mes))
        kpis.mes_pico = pico.mes
        kpis.mes_pico_nome = pico.nome_mes
        kpis.mes_vale = vale.mes
        kpis.mes_vale_nome = vale.nome_mes
        if vale.total_doses:
            kpis.amplitude = round(pico.total_doses / vale.total_doses, 2)

    return SazonalidadeResponse(kpis=kpis, meses=meses)
```

- [ ] **Step 5: Registrar o router em `main.py`**

Três edições em `backend/app/main.py`:

1. Junto dos outros imports de router:

```python
from app.routers.sazonalidade import router as sazonalidade_router
```

2. Ao final da lista `OPENAPI_TAGS`:

```python
    {
        "name": "Sazonalidade",
        "description": (
            "Volume de vacinação por mês do ano (Jan a Dez), com índice de "
            "sazonalidade, pico e vale, para apoiar o planejamento de campanhas."
        ),
    },
```

3. Junto dos outros `include_router`:

```python
app.include_router(sazonalidade_router)
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `pytest backend/tests/test_sazonalidade.py -v --no-cov`
Expected: PASS — 10 testes.

- [ ] **Step 7: Rodar a suíte completa do backend com cobertura**

Run: `pytest`
Expected: PASS com `Required test coverage of 100% reached`. Se `sazonalidade.py` aparecer com linhas faltando em `term-missing`, acrescente o teste do ramo faltante antes de commitar.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/sazonalidade.py backend/app/main.py backend/tests/test_sazonalidade.py
git commit -m "feat: RF17 endpoint de sazonalidade mensal"
```

---

### Task 2: Backend RF18 — endpoint `GET /alta-complexidade`

**Files:**
- Modify: `backend/app/schemas.py` (acrescentar ao final)
- Create: `backend/app/routers/alta_complexidade.py`
- Modify: `backend/app/main.py` (import, `OPENAPI_TAGS`, `include_router`)
- Test: `backend/tests/test_alta_complexidade.py`

**Interfaces:**
- Consumes: `app.database.get_db`, `app.dependencies.get_current_user`, `app.models.{Municipio, RegistroVacinacao, Vacina}`.
- Produces: `GET /alta-complexidade` com query param `top_municipios: int = 3`; resposta `AltaComplexidadeResponse` = `{"items": [...], "total_vacinas": int}`, cada item com `vacina_id`, `vacina_nome`, `total_doses`, `total_deslocamentos`, `taxa_deslocamento`, `centro_referencia_id`, `centro_referencia_nome`, `municipios: list[MunicipioAplicacaoItem]`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/test_alta_complexidade.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `pytest backend/tests/test_alta_complexidade.py -v --no-cov`
Expected: FAIL — 404, o endpoint ainda não existe.

- [ ] **Step 3: Acrescentar os schemas**

Ao final de `backend/app/schemas.py`:

```python


# ==========================================
# ALTA COMPLEXIDADE (RF18)
# ==========================================


class MunicipioAplicacaoItem(BaseModel):
    municipio_id: str
    municipio_nome: str
    total_doses: int
    percentual: float


class VacinaAltaComplexidadeItem(BaseModel):
    vacina_id: int
    vacina_nome: str
    total_doses: int
    total_deslocamentos: int
    taxa_deslocamento: float
    centro_referencia_id: Optional[str] = None
    centro_referencia_nome: Optional[str] = None
    municipios: list[MunicipioAplicacaoItem]


class AltaComplexidadeResponse(BaseModel):
    items: list[VacinaAltaComplexidadeItem]
    total_vacinas: int
```

- [ ] **Step 4: Criar o router**

Criar `backend/app/routers/alta_complexidade.py`:

```python
"""RF18 - Painel de imunobiológicos de alta complexidade.

Para cada vacina marcada com `alta_complexidade`, mostra a taxa de deslocamento
e os municípios de maior volume de aplicação - o primeiro deles é o centro de
referência regional.

A base de cálculo exclui DADO_INCONSISTENTE do numerador e do denominador - a
estatística mais defensável para este painel. Difere do `taxa_mobilidade` de
/dashboard/resumo, que usa base mista (denominador com inconsistentes,
numerador sem); por isso a taxa daqui pode divergir da taxa de mobilidade do
Dashboard para a mesma vacina - é decisão de projeto, não bug. A
`mv_fluxo_intermunicipal` não serve aqui: ela só contém registros com
deslocamento real, e a taxa precisa do denominador completo.
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Municipio, RegistroVacinacao, Vacina
from app.schemas import (
    AltaComplexidadeResponse,
    MunicipioAplicacaoItem,
    VacinaAltaComplexidadeItem,
)

router = APIRouter(prefix="/alta-complexidade", tags=["Alta Complexidade"])

TOP_MUNICIPIOS_PADRAO = 3
TOP_MUNICIPIOS_MAXIMO = 10


def _base_valida(db: Session, ids_vacinas: list[int]):
    """Registros que entram em todos os números desta tela."""
    return db.query(RegistroVacinacao).filter(
        RegistroVacinacao.ativo == True,
        RegistroVacinacao.status_dado != "DADO_INCONSISTENTE",
        RegistroVacinacao.vacina_id.in_(ids_vacinas),
    )


@router.get(
    "",
    response_model=AltaComplexidadeResponse,
    summary="Vacinas de alta complexidade e seus centros de referência",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def obter_alta_complexidade(
    top_municipios: int = TOP_MUNICIPIOS_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF18 - Lista as vacinas com `alta_complexidade = true` e `ativo = true`,
    da maior para a menor em volume de doses, com a taxa de deslocamento de cada
    uma e o ranking dos municípios de maior aplicação.

    Vacina de alta complexidade sem nenhum registro aparece zerada: escondê-la
    tiraria da vista justamente o caso que o gestor precisa investigar."""
    if top_municipios < 1:
        top_municipios = TOP_MUNICIPIOS_PADRAO
    if top_municipios > TOP_MUNICIPIOS_MAXIMO:
        top_municipios = TOP_MUNICIPIOS_MAXIMO

    vacinas = (
        db.query(Vacina)
        .filter(Vacina.alta_complexidade == True, Vacina.ativo == True)
        .all()
    )
    if not vacinas:
        return AltaComplexidadeResponse(items=[], total_vacinas=0)

    ids = [vacina.id for vacina in vacinas]

    totais = dict(
        _base_valida(db, ids)
        .with_entities(
            RegistroVacinacao.vacina_id,
            func.sum(RegistroVacinacao.quantidade),
        )
        .group_by(RegistroVacinacao.vacina_id)
        .all()
    )
    deslocamentos = dict(
        _base_valida(db, ids)
        .filter(RegistroVacinacao.teve_deslocamento == True)
        .with_entities(
            RegistroVacinacao.vacina_id,
            func.sum(RegistroVacinacao.quantidade),
        )
        .group_by(RegistroVacinacao.vacina_id)
        .all()
    )

    # Uma linha por (vacina, município), já ordenada por volume: o corte do
    # top N acontece em Python sobre este agregado, que é pequeno - são poucas
    # vacinas de alta complexidade. Window function não roda igual no SQLite.
    linhas_municipios = (
        _base_valida(db, ids)
        .join(Municipio, Municipio.id_ibge == RegistroVacinacao.municipio_vacina_id)
        .with_entities(
            RegistroVacinacao.vacina_id.label("vacina_id"),
            RegistroVacinacao.municipio_vacina_id.label("municipio_id"),
            Municipio.nome.label("municipio_nome"),
            func.sum(RegistroVacinacao.quantidade).label("total"),
        )
        .group_by(
            RegistroVacinacao.vacina_id,
            RegistroVacinacao.municipio_vacina_id,
            Municipio.nome,
        )
        .order_by(func.sum(RegistroVacinacao.quantidade).desc())
        .all()
    )
    por_vacina = defaultdict(list)
    for linha in linhas_municipios:
        por_vacina[linha.vacina_id].append(linha)

    items = []
    for vacina in vacinas:
        total = int(totais.get(vacina.id) or 0)
        deslocados = int(deslocamentos.get(vacina.id) or 0)
        municipios = [
            MunicipioAplicacaoItem(
                municipio_id=linha.municipio_id,
                municipio_nome=linha.municipio_nome,
                total_doses=int(linha.total),
                percentual=round(int(linha.total) / total * 100, 2),
            )
            for linha in por_vacina[vacina.id][:top_municipios]
        ]
        items.append(
            VacinaAltaComplexidadeItem(
                vacina_id=vacina.id,
                vacina_nome=vacina.nome,
                total_doses=total,
                total_deslocamentos=deslocados,
                taxa_deslocamento=round(deslocados / total * 100, 2) if total else 0.0,
                centro_referencia_id=municipios[0].municipio_id if municipios else None,
                centro_referencia_nome=municipios[0].municipio_nome if municipios else None,
                municipios=municipios,
            )
        )

    items.sort(key=lambda item: (-item.total_doses, item.vacina_nome))
    return AltaComplexidadeResponse(items=items, total_vacinas=len(items))
```

- [ ] **Step 5: Registrar o router em `main.py`**

Três edições em `backend/app/main.py`:

1. Junto dos outros imports de router:

```python
from app.routers.alta_complexidade import router as alta_complexidade_router
```

2. Ao final da lista `OPENAPI_TAGS`:

```python
    {
        "name": "Alta Complexidade",
        "description": (
            "Vacinas de alta complexidade: taxa de deslocamento de cada uma e os "
            "municípios de maior volume de aplicação (centros de referência)."
        ),
    },
```

3. Junto dos outros `include_router`:

```python
app.include_router(alta_complexidade_router)
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `pytest backend/tests/test_alta_complexidade.py -v --no-cov`
Expected: PASS — 9 testes.

- [ ] **Step 7: Rodar a suíte completa do backend com cobertura**

Run: `pytest`
Expected: PASS com 100% de cobertura.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/alta_complexidade.py backend/app/main.py backend/tests/test_alta_complexidade.py
git commit -m "feat: RF18 endpoint de imunobiologicos de alta complexidade"
```

---

### Task 3: Frontend — cliente HTTP e cache dos dois painéis

**Files:**
- Modify: `frontend/api_client.py` (acrescentar ao final)
- Modify: `frontend/data_cache.py` (imports e dois envoltórios novos)
- Test: `frontend/tests/test_paineis_api.py` (criar)
- Test: `frontend/tests/test_data_cache.py` (acrescentar à fixture e novos testes)

**Interfaces:**
- Consumes: `GET /sazonalidade` e `GET /alta-complexidade` da Task 1 e da Task 2; `api_client._request`.
- Produces:
  - `api_client.obter_sazonalidade(token, vacina_id=None, municipio_id=None, ano_inicio=None, ano_fim=None) -> dict`
  - `api_client.obter_alta_complexidade(token, top_municipios=3) -> dict`
  - `data_cache.sazonalidade(token, vacina_id=None, municipio_id=None, ano_inicio=None, ano_fim=None) -> dict`
  - `data_cache.alta_complexidade(token, top_municipios=3) -> dict`

- [ ] **Step 1: Escrever os testes do cliente HTTP**

Criar `frontend/tests/test_paineis_api.py`:

```python
"""RF17/RF18 - Montagem dos parâmetros das chamadas dos dois painéis novos."""

from unittest.mock import patch

from api_client import obter_alta_complexidade, obter_sazonalidade


@patch("api_client._request")
def test_sazonalidade_sem_filtros_nao_envia_parametros(mock_request):
    mock_request.return_value = {"meses": []}

    obter_sazonalidade("tk")

    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/sazonalidade"
    assert kwargs["params"] == {}


@patch("api_client._request")
def test_sazonalidade_envia_todos_os_filtros(mock_request):
    mock_request.return_value = {"meses": []}

    obter_sazonalidade(
        "tk", vacina_id=7, municipio_id="2304400", ano_inicio=2023, ano_fim=2024
    )

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {
        "vacina_id": 7,
        "municipio_id": "2304400",
        "ano_inicio": 2023,
        "ano_fim": 2024,
    }


@patch("api_client._request")
def test_alta_complexidade_envia_o_top_municipios(mock_request):
    mock_request.return_value = {"items": []}

    obter_alta_complexidade("tk", top_municipios=5)

    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert args[1] == "/alta-complexidade"
    assert kwargs["params"] == {"top_municipios": 5}


@patch("api_client._request")
def test_alta_complexidade_tem_padrao_de_tres(mock_request):
    mock_request.return_value = {"items": []}

    obter_alta_complexidade("tk")

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {"top_municipios": 3}
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run (dentro de `frontend/`): `pytest tests/test_paineis_api.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'obter_sazonalidade'`.

- [ ] **Step 3: Acrescentar as funções ao `api_client.py`**

Ao final de `frontend/api_client.py`:

```python


# --- SAZONALIDADE (RF17) ---


def obter_sazonalidade(
    token: str,
    vacina_id: Optional[int] = None,
    municipio_id: Optional[str] = None,
    ano_inicio: Optional[int] = None,
    ano_fim: Optional[int] = None,
) -> dict:
    params: dict[str, Any] = {}
    if vacina_id:
        params["vacina_id"] = vacina_id
    if municipio_id:
        params["municipio_id"] = municipio_id
    if ano_inicio:
        params["ano_inicio"] = ano_inicio
    if ano_fim:
        params["ano_fim"] = ano_fim
    return _request("GET", "/sazonalidade", token, params=params)


# --- ALTA COMPLEXIDADE (RF18) ---


def obter_alta_complexidade(token: str, top_municipios: int = 3) -> dict:
    return _request(
        "GET", "/alta-complexidade", token, params={"top_municipios": top_municipios}
    )
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `pytest tests/test_paineis_api.py -v --no-cov`
Expected: PASS — 4 testes.

- [ ] **Step 5: Escrever os testes do cache**

Em `frontend/tests/test_data_cache.py`, acrescentar `data_cache.sazonalidade` e `data_cache.alta_complexidade` à tupla da fixture `_limpar_cache`:

```python
    for funcao in (
        data_cache.listar_municipios_resumido,
        data_cache.listar_vacinas_resumido,
        data_cache.fluxo_intermunicipal,
        data_cache.ranking_fluxo,
        data_cache.resumo_dashboard,
        data_cache.alertas_completude,
        data_cache.sazonalidade,
        data_cache.alta_complexidade,
    ):
```

E acrescentar ao final do arquivo:

```python


@patch("data_cache.obter_sazonalidade")
def test_sazonalidade_repassa_os_filtros(mock_obter):
    mock_obter.return_value = {"kpis": {}, "meses": []}

    data_cache.sazonalidade(
        "token", vacina_id=7, municipio_id="2304400", ano_inicio=2023, ano_fim=2024
    )

    assert mock_obter.call_args.kwargs == {
        "vacina_id": 7,
        "municipio_id": "2304400",
        "ano_inicio": 2023,
        "ano_fim": 2024,
    }


@patch("data_cache.obter_sazonalidade")
def test_sazonalidade_nao_repete_a_chamada_http(mock_obter):
    mock_obter.return_value = {"kpis": {}, "meses": []}

    data_cache.sazonalidade("token")
    data_cache.sazonalidade("token")

    assert mock_obter.call_count == 1


@patch("data_cache.obter_alta_complexidade")
def test_alta_complexidade_repassa_o_top_municipios(mock_obter):
    mock_obter.return_value = {"items": [], "total_vacinas": 0}

    data_cache.alta_complexidade("token", top_municipios=5)

    assert mock_obter.call_args.kwargs == {"top_municipios": 5}
```

- [ ] **Step 6: Rodar e confirmar que falha**

Run: `pytest tests/test_data_cache.py -v --no-cov`
Expected: FAIL — `AttributeError: module 'data_cache' has no attribute 'sazonalidade'`.

- [ ] **Step 7: Acrescentar os envoltórios ao `data_cache.py`**

Acrescentar aos imports vindos de `api_client` (mantendo a ordem alfabética existente):

```python
from api_client import (
    listar_alertas_completude,
    listar_todos_municipios,
    listar_vacinas,
    obter_alta_complexidade,
    obter_fluxo_intermunicipal,
    obter_ranking_fluxo,
    obter_resumo_dashboard,
    obter_sazonalidade,
)
```

E ao final do arquivo:

```python


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def sazonalidade(
    token: str, vacina_id=None, municipio_id=None, ano_inicio=None, ano_fim=None
) -> dict:
    """RF17 - Agregado de 12 linhas; o TTL só evita repetir a consulta a cada
    rerun do Streamlit."""
    return obter_sazonalidade(
        token,
        vacina_id=vacina_id,
        municipio_id=municipio_id,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
    )


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def alta_complexidade(token: str, top_municipios: int = 3) -> dict:
    """RF18 - Poucas vacinas por resposta, mesmo TTL dos demais agregados."""
    return obter_alta_complexidade(token, top_municipios=top_municipios)
```

- [ ] **Step 8: Rodar os dois arquivos e confirmar que passam**

Run: `pytest tests/test_data_cache.py tests/test_paineis_api.py -v --no-cov`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/api_client.py frontend/data_cache.py frontend/tests/test_paineis_api.py frontend/tests/test_data_cache.py
git commit -m "feat: cliente HTTP e cache dos paineis de sazonalidade e alta complexidade"
```

Nota: a suíte completa do frontend só volta a 100% de cobertura na Task 5, quando as duas telas existirem. Rodar `pytest` inteiro aqui vai falhar no `--cov-fail-under=100` — use `--no-cov` até lá.

---

### Task 4: Frontend RF17 — tela de sazonalidade e item de navegação

**Files:**
- Create: `frontend/sazonalidade_ui.py`
- Modify: `frontend/app.py` (import, dicionário `PAGINAS`, roteamento)
- Test: `frontend/tests/test_sazonalidade_ui.py`

**Interfaces:**
- Consumes: `data_cache.sazonalidade`, `data_cache.listar_municipios_resumido`, `data_cache.listar_vacinas_resumido`, `api_client.ApiError`.
- Produces: `sazonalidade_ui.render_sazonalidade_section()`; chave de página `"sazonalidade"` em `st.session_state["pagina_ativa"]`; chaves de widget `saz_vacina`, `saz_municipio`, `saz_ano_inicio`, `saz_ano_fim`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `frontend/tests/test_sazonalidade_ui.py`:

```python
"""RF17 - Tela de sazonalidade."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]
_VACINAS = [(1, "COVID-19"), (2, "Influenza")]

_NOMES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
          "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _payload(totais=None):
    """Por padrão: 10, 20, ... 120 doses. Média 65, pico Dez, vale Jan."""
    totais = totais if totais is not None else [mes * 10 for mes in range(1, 13)]
    total_periodo = sum(totais)
    media = total_periodo / 12
    meses = [
        {
            "mes": numero,
            "nome_mes": _NOMES[numero - 1],
            "total_doses": totais[numero - 1],
            "indice_sazonalidade": round(totais[numero - 1] / media, 2) if media else 0.0,
        }
        for numero in range(1, 13)
    ]
    return {
        "kpis": {
            "total_periodo": total_periodo,
            "media_mensal": round(media, 2),
            "mes_pico": 12,
            "mes_pico_nome": "Dez",
            "mes_vale": 1,
            "mes_vale_nome": "Jan",
            "amplitude": 12.0,
        },
        "meses": meses,
    }


def _vazio():
    dados = _payload(totais=[0] * 12)
    dados["kpis"].update(
        {"mes_pico": None, "mes_pico_nome": None, "mes_vale": None,
         "mes_vale_nome": None, "amplitude": 0.0}
    )
    return dados


def _abrir():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "sazonalidade"
    return at


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_tela_mostra_titulo_kpis_e_tabela(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Sazonalidade" in textos
    assert "Dez" in textos
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Mês de pico"] == "Dez"
    assert valores["Mês de vale"] == "Jan"
    assert valores["Amplitude"] == "12.0x"
    assert valores["Total do período"] == "780"


@patch("sazonalidade_ui.st.bar_chart")
@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_grafico_recebe_os_doze_meses_em_ordem(
    mock_saz, mock_municipios, mock_vacinas, mock_chart
):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    dados = mock_chart.call_args.args[0]
    assert list(dados.index) == [
        f"{numero:02d} {nome}" for numero, nome in zip(range(1, 13), _NOMES)
    ], "o prefixo numérico é o que mantém o eixo em ordem cronológica"
    assert list(dados["Doses"]) == [mes * 10 for mes in range(1, 13)]


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtros_sao_repassados_a_api(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_vacina").select("Influenza (ID: 2)").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["vacina_id"] == 2


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtro_de_municipio_e_repassado(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_municipio").select("Fortaleza (2304400)").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["municipio_id"] == "2304400"


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_filtros_de_ano_sao_repassados(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_ano_inicio").select("2023").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["ano_inicio"] == 2023
    assert mock_saz.call_args.kwargs["ano_fim"] is None


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_ano_fim_e_repassado(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _payload()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()
    at.selectbox(key="saz_ano_fim").select("2024").run()

    assert not at.exception
    assert mock_saz.call_args.kwargs["ano_fim"] == 2024


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_periodo_sem_dado_mostra_aviso(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.return_value = _vazio()
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    assert any("Não há registros" in (i.value or "") for i in at.info)
    assert len(at.metric) == 0


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_erro_da_api_exibe_mensagem(mock_saz, mock_municipios, mock_vacinas):
    mock_saz.side_effect = ApiError("Servidor indisponível.")
    mock_municipios.return_value = _MUNICIPIOS
    mock_vacinas.return_value = _VACINAS

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("sazonalidade_ui.listar_vacinas_resumido")
@patch("sazonalidade_ui.listar_municipios_resumido")
@patch("sazonalidade_ui.sazonalidade")
def test_listas_de_apoio_indisponiveis_nao_quebram_a_tela(
    mock_saz, mock_municipios, mock_vacinas
):
    mock_saz.return_value = _payload()
    mock_municipios.side_effect = ApiError("Servidor indisponível.")
    mock_vacinas.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert mock_saz.called


@patch("sazonalidade_ui.sazonalidade")
@patch("sazonalidade_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_saz):
    import streamlit as st

    import sazonalidade_ui

    st.session_state.clear()
    sazonalidade_ui.render_sazonalidade_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para visualizar a sazonalidade."
    )
    mock_saz.assert_not_called()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run (dentro de `frontend/`): `pytest tests/test_sazonalidade_ui.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'sazonalidade_ui'`.

- [ ] **Step 3: Criar a tela**

Criar `frontend/sazonalidade_ui.py`:

```python
"""RF17 - Painel de sazonalidade.

Mostra o volume de doses por mês do ano (Jan..Dez), consolidando todos os anos
do recorte. A série cronológica ano-a-mês já está no Dashboard Geral; aqui a
pergunta é "em qual mês do ano concentrar a campanha".

O eixo do gráfico usa rótulos "01 Jan", "02 Fev"...: o eixo nominal do Streamlit
ordena alfabeticamente, e o prefixo numérico é o que garante a ordem
cronológica sem depender do comportamento padrão do componente.
"""

import pandas as pd
import streamlit as st

from api_client import ApiError
from data_cache import listar_municipios_resumido, listar_vacinas_resumido, sazonalidade

OPCOES_ANO = ["Todos", "2026", "2025", "2024", "2023", "2022", "2021", "2020"]


def _formatar_numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _dados_apoio(token):
    """Listas dos seletores. A tela continua útil se alguma delas falhar."""
    try:
        municipios = listar_municipios_resumido(token)
    except ApiError:
        municipios = []
    try:
        vacinas = listar_vacinas_resumido(token)
    except ApiError:
        vacinas = []
    return municipios, vacinas


def _render_filtros(municipios, vacinas):
    opcoes_mun = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
    opcoes_vac = ["Todas"] + [f"{nome} (ID: {vid})" for vid, nome in vacinas]

    with st.container(border=True):
        col_vac, col_mun, col_de, col_ate = st.columns([2, 2, 1, 1])
        vac_raw = col_vac.selectbox("Imunobiológico", opcoes_vac, key="saz_vacina")
        mun_raw = col_mun.selectbox(
            "Município de Aplicação", opcoes_mun, key="saz_municipio"
        )
        ano_inicio_raw = col_de.selectbox("De (ano)", OPCOES_ANO, key="saz_ano_inicio")
        ano_fim_raw = col_ate.selectbox("Até (ano)", OPCOES_ANO, key="saz_ano_fim")

    vacina_id = None
    if vac_raw != "Todas":
        vacina_id = int(vac_raw.split("ID: ")[-1].replace(")", "").strip())

    municipio_id = None
    if mun_raw != "Todos":
        municipio_id = mun_raw.split("(")[-1].replace(")", "").strip()

    ano_inicio = None if ano_inicio_raw == "Todos" else int(ano_inicio_raw)
    ano_fim = None if ano_fim_raw == "Todos" else int(ano_fim_raw)

    return vacina_id, municipio_id, ano_inicio, ano_fim


def _render_kpis(kpis):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with st.container(border=True):
            st.metric("Mês de pico", kpis["mes_pico_nome"])
    with col2:
        with st.container(border=True):
            st.metric("Mês de vale", kpis["mes_vale_nome"])
    with col3:
        with st.container(border=True):
            st.metric("Amplitude", f"{kpis['amplitude']}x")
    with col4:
        with st.container(border=True):
            st.metric("Total do período", _formatar_numero(kpis["total_periodo"]))


def _render_grafico(meses):
    dados = pd.DataFrame(
        {
            "Mês": [f"{mes['mes']:02d} {mes['nome_mes']}" for mes in meses],
            "Doses": [mes["total_doses"] for mes in meses],
        }
    ).set_index("Mês")
    st.bar_chart(dados, height=340, use_container_width=True)


def _marca(mes, kpis) -> str:
    if mes["mes"] == kpis["mes_pico"]:
        return "▲ pico"
    if mes["mes"] == kpis["mes_vale"]:
        return "▼ vale"
    return ""


def _render_tabela(meses, kpis):
    cabecalho = st.columns([1.5, 2, 2, 1.5])
    for coluna, titulo in zip(cabecalho, ["Mês", "Doses", "Índice", ""]):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for mes in meses:
        colunas = st.columns([1.5, 2, 2, 1.5])
        colunas[0].markdown(mes["nome_mes"])
        colunas[1].markdown(_formatar_numero(mes["total_doses"]))
        colunas[2].markdown(f"{mes['indice_sazonalidade']:.2f}")
        colunas[3].markdown(_marca(mes, kpis))


def render_sazonalidade_section():
    """RF17 - Painel de sazonalidade."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar a sazonalidade.")
        return

    st.markdown(
        '<div class="page-title">📅 Sazonalidade da Vacinação</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Volume de doses por mês do ano, consolidando '
        "todo o período filtrado. O índice compara cada mês com a média mensal "
        "(1,00 = mês médio).</div>",
        unsafe_allow_html=True,
    )

    municipios, vacinas = _dados_apoio(token)
    vacina_id, municipio_id, ano_inicio, ano_fim = _render_filtros(municipios, vacinas)

    try:
        dados = sazonalidade(
            token,
            vacina_id=vacina_id,
            municipio_id=municipio_id,
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
        )
    except ApiError as exc:
        st.error(f"Erro ao carregar o painel de sazonalidade: {exc.message}")
        return

    kpis = dados["kpis"]
    if kpis["total_periodo"] == 0:
        st.info("Não há registros de vacinação para os filtros selecionados.")
        return

    _render_kpis(kpis)
    st.markdown("<hr>", unsafe_allow_html=True)
    _render_grafico(dados["meses"])
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    _render_tabela(dados["meses"], kpis)
```

- [ ] **Step 4: Ligar a tela à navegação**

Três edições em `frontend/app.py`:

1. Junto dos outros imports de tela (ordem alfabética):

```python
from sazonalidade_ui import render_sazonalidade_section
```

2. No dicionário `PAGINAS`, entre `fluxo` e `completude`:

```python
    PAGINAS = {
        "dashboard": "📊 Dashboard Geral",
        "fluxo": "🔀 Fluxo Intermunicipal",
        "sazonalidade": "📅 Sazonalidade",
        "completude": "⚠️ Alertas de Completude",
        "registros": "💉 Registros de Vacinação",
        "municipios": "🏙️ Gestão de Municípios & Vacinas",
    }
```

3. No roteamento central, um ramo novo depois de `fluxo`:

```python
    elif st.session_state["pagina_ativa"] == "sazonalidade":
        render_sazonalidade_section()
```

- [ ] **Step 5: Rodar os testes da tela**

Run: `pytest tests/test_sazonalidade_ui.py -v --no-cov`
Expected: PASS — 10 testes.

- [ ] **Step 6: Commit**

```bash
git add frontend/sazonalidade_ui.py frontend/app.py frontend/tests/test_sazonalidade_ui.py
git commit -m "feat: RF17 tela de sazonalidade e item de navegacao"
```

---

### Task 5: Frontend RF18 — tela de alta complexidade, navegação e fechamento da cobertura

**Files:**
- Create: `frontend/alta_complexidade_ui.py`
- Modify: `frontend/app.py` (import, `PAGINAS`, roteamento)
- Test: `frontend/tests/test_alta_complexidade_ui.py`

**Interfaces:**
- Consumes: `data_cache.alta_complexidade`, `api_client.ApiError`, `theme.badge_html`.
- Produces: `alta_complexidade_ui.render_alta_complexidade_section()`; chave de página `"alta_complexidade"`; chave de widget `alta_top_municipios`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `frontend/tests/test_alta_complexidade_ui.py`:

```python
"""RF18 - Tela de imunobiológicos de alta complexidade."""

from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError


def _payload():
    """Quatro vacinas cobrindo os três tons de badge e o caso sem registro."""
    return {
        "items": [
            {
                "vacina_id": 1,
                "vacina_nome": "Imunoglobulina",
                "total_doses": 200,
                "total_deslocamentos": 130,
                "taxa_deslocamento": 65.0,
                "centro_referencia_id": "2304400",
                "centro_referencia_nome": "Fortaleza",
                "municipios": [
                    {"municipio_id": "2304400", "municipio_nome": "Fortaleza",
                     "total_doses": 150, "percentual": 75.0},
                    {"municipio_id": "2312908", "municipio_nome": "Sobral",
                     "total_doses": 30, "percentual": 15.0},
                    {"municipio_id": "2303709", "municipio_nome": "Caucaia",
                     "total_doses": 20, "percentual": 10.0},
                ],
            },
            {
                "vacina_id": 2,
                "vacina_nome": "Raiva humana",
                "total_doses": 100,
                "total_deslocamentos": 30,
                "taxa_deslocamento": 30.0,
                "centro_referencia_id": "2312908",
                "centro_referencia_nome": "Sobral",
                "municipios": [
                    {"municipio_id": "2312908", "municipio_nome": "Sobral",
                     "total_doses": 100, "percentual": 100.0},
                ],
            },
            {
                "vacina_id": 3,
                "vacina_nome": "Palivizumabe",
                "total_doses": 40,
                "total_deslocamentos": 4,
                "taxa_deslocamento": 10.0,
                "centro_referencia_id": "2304400",
                "centro_referencia_nome": "Fortaleza",
                "municipios": [
                    {"municipio_id": "2304400", "municipio_nome": "Fortaleza",
                     "total_doses": 40, "percentual": 100.0},
                ],
            },
            {
                "vacina_id": 4,
                "vacina_nome": "Soro antirrábico",
                "total_doses": 0,
                "total_deslocamentos": 0,
                "taxa_deslocamento": 0.0,
                "centro_referencia_id": None,
                "centro_referencia_nome": None,
                "municipios": [],
            },
        ],
        "total_vacinas": 4,
    }


def _abrir():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = "ADMIN"
    at.session_state["municipio_id"] = None
    at.session_state["pagina_ativa"] = "alta_complexidade"
    return at


@patch("alta_complexidade_ui.alta_complexidade")
def test_tela_lista_as_vacinas_e_os_centros(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Alta Complexidade" in textos
    assert "Imunoglobulina" in textos
    assert "Fortaleza" in textos
    assert "65.0%" in textos
    assert "—" in textos, "vacina sem registro não tem centro de referência"


@patch("alta_complexidade_ui.alta_complexidade")
def test_tela_mostra_os_kpis_ponderados(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Vacinas de alta complexidade"] == "4"
    assert valores["Doses aplicadas"] == "340"
    assert valores["Taxa geral de deslocamento"] == "48.24%", "164 / 340"


@patch("alta_complexidade_ui.alta_complexidade")
def test_cada_vacina_tem_o_ranking_de_municipios(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()

    assert not at.exception
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Sobral (2312908)" in textos
    assert "Caucaia (2303709)" in textos
    assert any("Nenhuma dose registrada" in (c.value or "") for c in at.caption)


@patch("alta_complexidade_ui.alta_complexidade")
def test_seletor_de_top_municipios_e_repassado(mock_dados):
    mock_dados.return_value = _payload()

    at = _abrir().run()
    at.selectbox(key="alta_top_municipios").select(10).run()

    assert not at.exception
    assert mock_dados.call_args.kwargs["top_municipios"] == 10


@patch("alta_complexidade_ui.alta_complexidade")
def test_taxa_geral_com_zero_doses_nao_divide_por_zero(mock_dados):
    dados = _payload()
    dados["items"] = [dados["items"][-1]]
    dados["total_vacinas"] = 1
    mock_dados.return_value = dados

    at = _abrir().run()

    assert not at.exception
    valores = {m.label: str(m.value) for m in at.metric}
    assert valores["Taxa geral de deslocamento"] == "0.0%"


@patch("alta_complexidade_ui.alta_complexidade")
def test_sem_vacinas_de_alta_complexidade_mostra_aviso(mock_dados):
    mock_dados.return_value = {"items": [], "total_vacinas": 0}

    at = _abrir().run()

    assert not at.exception
    assert any("Nenhuma vacina" in (i.value or "") for i in at.info)
    assert len(at.metric) == 0


@patch("alta_complexidade_ui.alta_complexidade")
def test_erro_da_api_exibe_mensagem(mock_dados):
    mock_dados.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("alta_complexidade_ui.alta_complexidade")
@patch("alta_complexidade_ui.st.warning")
def test_tela_sem_token_avisa_e_nao_consulta(mock_warning, mock_dados):
    import streamlit as st

    import alta_complexidade_ui

    st.session_state.clear()
    alta_complexidade_ui.render_alta_complexidade_section()

    mock_warning.assert_called_once_with(
        "É necessário estar autenticado para visualizar este painel."
    )
    mock_dados.assert_not_called()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `pytest tests/test_alta_complexidade_ui.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'alta_complexidade_ui'`.

- [ ] **Step 3: Criar a tela**

Criar `frontend/alta_complexidade_ui.py`:

```python
"""RF18 - Painel de imunobiológicos de alta complexidade.

Uma linha por vacina de alta complexidade, com a taxa de deslocamento e o
município que funciona como centro de referência regional; o expander de cada
linha abre o ranking completo dos municípios de maior aplicação.
"""

import streamlit as st

from api_client import ApiError
from data_cache import alta_complexidade
from theme import badge_html

OPCOES_TOP = [3, 5, 10]


def _formatar_numero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _tom_taxa(taxa: float) -> str:
    """Acima de 50% a vacina é majoritariamente aplicada fora do município de
    residência do paciente - o sinal de centro de referência regional."""
    if taxa > 50:
        return "danger"
    if taxa >= 25:
        return "warning"
    return "neutral"


def _render_kpis(itens):
    total_doses = sum(item["total_doses"] for item in itens)
    total_deslocamentos = sum(item["total_deslocamentos"] for item in itens)
    # Ponderada pelo volume: uma vacina com 20 doses não pode pesar o mesmo que
    # uma com 20 mil na taxa geral.
    taxa_geral = (
        round(total_deslocamentos / total_doses * 100, 2) if total_doses else 0.0
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.metric("Vacinas de alta complexidade", len(itens))
    with col2:
        with st.container(border=True):
            st.metric("Doses aplicadas", _formatar_numero(total_doses))
    with col3:
        with st.container(border=True):
            st.metric("Taxa geral de deslocamento", f"{taxa_geral}%")


def _render_ranking(item):
    if not item["municipios"]:
        st.caption("Nenhuma dose registrada para esta vacina no período.")
        return
    for posicao, municipio in enumerate(item["municipios"], start=1):
        linha = st.columns([0.6, 3, 1.6, 1.6])
        linha[0].markdown(f"{posicao}º")
        linha[1].markdown(
            f"{municipio['municipio_nome']} ({municipio['municipio_id']})"
        )
        linha[2].markdown(_formatar_numero(municipio["total_doses"]))
        linha[3].markdown(f"{municipio['percentual']}%")


def _render_vacina(item):
    colunas = st.columns([3, 1.6, 1.6, 2.4])
    colunas[0].markdown(f"**{item['vacina_nome']}**")
    colunas[1].markdown(_formatar_numero(item["total_doses"]))
    colunas[2].markdown(
        badge_html(
            f"{item['taxa_deslocamento']}%", _tom_taxa(item["taxa_deslocamento"])
        ),
        unsafe_allow_html=True,
    )
    colunas[3].markdown(item["centro_referencia_nome"] or "—")

    with st.expander(f"Municípios de aplicação — {item['vacina_nome']}"):
        _render_ranking(item)


def render_alta_complexidade_section():
    """RF18 - Painel de imunobiológicos de alta complexidade."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar este painel.")
        return

    st.markdown(
        '<div class="page-title">🧬 Imunobiológicos de Alta Complexidade</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="page-subtitle">Taxa de deslocamento de cada vacina e os '
        "municípios que funcionam como centro de referência regional.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        top_municipios = st.selectbox(
            "Municípios por vacina", OPCOES_TOP, key="alta_top_municipios"
        )

    try:
        dados = alta_complexidade(token, top_municipios=int(top_municipios))
    except ApiError as exc:
        st.error(f"Erro ao carregar o painel de alta complexidade: {exc.message}")
        return

    itens = dados["items"]
    if not itens:
        st.info(
            "Nenhuma vacina marcada como alta complexidade. Marque a opção em "
            "Gestão de Municípios & Vacinas."
        )
        return

    _render_kpis(itens)
    st.markdown("<hr>", unsafe_allow_html=True)
    cabecalho = st.columns([3, 1.6, 1.6, 2.4])
    for coluna, titulo in zip(
        cabecalho, ["Vacina", "Doses", "Deslocamento", "Centro de referência"]
    ):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for item in itens:
        _render_vacina(item)
```

- [ ] **Step 4: Ligar a tela à navegação**

Três edições em `frontend/app.py`:

1. Junto dos outros imports de tela:

```python
from alta_complexidade_ui import render_alta_complexidade_section
```

2. No dicionário `PAGINAS`, depois de `sazonalidade`:

```python
    PAGINAS = {
        "dashboard": "📊 Dashboard Geral",
        "fluxo": "🔀 Fluxo Intermunicipal",
        "sazonalidade": "📅 Sazonalidade",
        "alta_complexidade": "🧬 Alta Complexidade",
        "completude": "⚠️ Alertas de Completude",
        "registros": "💉 Registros de Vacinação",
        "municipios": "🏙️ Gestão de Municípios & Vacinas",
    }
```

3. No roteamento central, depois do ramo de `sazonalidade`:

```python
    elif st.session_state["pagina_ativa"] == "alta_complexidade":
        render_alta_complexidade_section()
```

- [ ] **Step 5: Rodar os testes da tela**

Run: `pytest tests/test_alta_complexidade_ui.py -v --no-cov`
Expected: PASS — 8 testes.

- [ ] **Step 6: Rodar a suíte completa do frontend com cobertura**

Run (dentro de `frontend/`): `pytest`
Expected: PASS com `Required test coverage of 100% reached`. Se `term-missing` apontar linhas descobertas em `sazonalidade_ui.py`, `alta_complexidade_ui.py`, `api_client.py` ou `data_cache.py`, escreva o teste do ramo faltante antes de commitar — não baixe o limite de cobertura.

- [ ] **Step 7: Rodar a suíte completa do backend**

Run (na raiz do repositório): `pytest`
Expected: PASS com 100% de cobertura — confirma que nada nas Tasks 3 a 5 quebrou o backend.

- [ ] **Step 8: Commit**

```bash
git add frontend/alta_complexidade_ui.py frontend/app.py frontend/tests/test_alta_complexidade_ui.py
git commit -m "feat: RF18 tela de imunobiologicos de alta complexidade"
```

---

## Verificação final

Depois da Task 5, com o Docker Compose de desenvolvimento no ar (`docker compose up`), abrir `http://localhost:8501`, entrar com um usuário ADMIN e conferir na tela:

1. Os itens **📅 Sazonalidade** e **🧬 Alta Complexidade** aparecem na navegação lateral, entre Fluxo Intermunicipal e Alertas de Completude.
2. Sazonalidade: as doze barras aparecem em ordem de Jan a Dez, os KPIs de pico/vale batem com a maior e a menor barra, e trocar o filtro de vacina muda o gráfico.
3. Alta Complexidade: cada vacina listada tem `alta_complexidade = true` em Gestão de Vacinas, e o centro de referência exibido é o primeiro município do expander.
4. `http://localhost:8000/docs` mostra as tags **Sazonalidade** e **Alta Complexidade** com os dois endpoints documentados.
