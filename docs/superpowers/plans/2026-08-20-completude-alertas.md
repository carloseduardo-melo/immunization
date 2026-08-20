# RF15 & RF16 — Completude e Alertas: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar automaticamente meses/municípios com volume de registros fora da faixa esperada, gravar alertas em `alertas_completude`, e permitir que um administrador liste e trate esses alertas por uma tela nova.

**Architecture:** Um serviço puro (`backend/app/services/completude.py`) agrega os totais mensais por município no banco, calcula média e desvio-padrão em Python e faz upsert dos alertas. Um router (`backend/app/routers/completude.py`) expõe a varredura, a listagem e a mudança de status com RBAC. No frontend, `frontend/completude_ui.py` renderiza a tela, ligada por uma entrada nova no menu de `frontend/app.py`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.x, Pydantic v2, pytest, Streamlit, `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-08-20-completude-alertas-design.md`

## Global Constraints

- **Cobertura backend 100%.** `pytest.ini` na raiz usa `--cov=app --cov-fail-under=100` com `branch = True`. Toda linha e todo ramo de código novo em `backend/app/` precisa de teste, ou a suíte inteira falha.
- **Cobertura frontend 100%.** `frontend/pytest.ini` usa `--cov=. --cov-fail-under=100` com testpaths `tests`. Rodar com `cd frontend && python -m pytest`.
- **Backend roda em SQLite (testes) e PostgreSQL (produção).** Nada de SQL específico de dialeto: sem `stddev`, sem `date_trunc`. Use `func.extract`, como em `backend/app/routers/dashboard.py:56`.
- **Nenhuma migration nova.** A tabela `alertas_completude` já existe (`alembic/versions/b6b6414f1b16_schema.py`) e o model `AlertaCompletude` já está em `backend/app/models.py:130`.
- **Status permitidos:** exatamente `ABERTO`, `INVESTIGANDO`, `RESOLVIDO`, `FALSO_POSITIVO` (CHECK `chk_alerta_status` no banco).
- **Prettier no CI.** `npm run format:check` cobre `**/*.md`, `**/*.json`, `**/*.yml`. Se tocar num desses, rode `npx prettier --write <arquivo>` antes de commitar. Arquivos `.py` não passam pelo prettier.
- **Commits sem trailer de co-autoria.** Mensagem no padrão Conventional Commits (`feat:`, `test:`, `docs:`), sem `Co-Authored-By`.
- **Textos em português** (mensagens de erro da API e rótulos de UI), como no resto do projeto.
- **Parâmetros da regra:** `k = 2.0` (multiplicador do desvio) e `minimo_meses = 3` são os padrões.

---

## Estrutura de arquivos

| Arquivo                                | Responsabilidade                                                   |
| -------------------------------------- | ------------------------------------------------------------------ |
| `backend/app/services/__init__.py`     | pacote novo (vazio)                                                |
| `backend/app/services/completude.py`   | regra de detecção e upsert dos alertas; sem dependência de FastAPI |
| `backend/app/routers/completude.py`    | endpoints POST/GET/PUT, RBAC, paginação                            |
| `backend/app/schemas.py`               | + bloco de schemas de completude                                   |
| `backend/app/main.py`                  | + tag OpenAPI e `include_router`                                   |
| `backend/tests/test_completude.py`     | testes do serviço e dos endpoints                                  |
| `frontend/api_client.py`               | + três funções HTTP de completude                                  |
| `frontend/data_cache.py`               | + wrapper com cache da listagem                                    |
| `frontend/theme.py`                    | + tom `danger` em `BADGE_TONES`                                    |
| `frontend/completude_ui.py`            | tela: KPIs, filtros, tabela, ações de ADMIN                        |
| `frontend/app.py`                      | + item de menu e ramo de roteamento                                |
| `frontend/tests/test_completude_ui.py` | testes da tela via `AppTest`                                       |

---

### Task 1: Serviço de detecção de anomalias (RF15)

**Files:**

- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/completude.py`
- Modify: `backend/app/schemas.py` (acrescentar bloco no fim do arquivo)
- Test: `backend/tests/test_completude.py`

**Interfaces:**

- Consumes: `app.models.AlertaCompletude`, `app.models.RegistroVacinacao` (já existentes).
- Produces:
  - `detectar_anomalias(db: Session, k: float = 2.0, minimo_meses: int = 3) -> ResultadoVarredura`
  - `K_PADRAO = 2.0`, `MINIMO_MESES = 3`
  - Schemas `AlertaCompletudeOut`, `AlertaStatusUpdate`, `PaginatedAlertas`, `ResultadoVarredura`.

- [ ] **Step 1: Escrever os testes do serviço (falhando)**

Crie `backend/tests/test_completude.py`:

```python
from datetime import date

from app.models import AlertaCompletude, Municipio, RegistroVacinacao
from app.services.completude import detectar_anomalias


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
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `python -m pytest backend/tests/test_completude.py -v --no-cov`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Acrescentar os schemas**

No fim de `backend/app/schemas.py`, acrescente o bloco (e adicione `Literal` ao `from typing import ...` já existente no topo, que hoje importa só `Optional`):

```python
# ==========================================
# COMPLETUDE (RF15 & RF16)
# ==========================================


class AlertaCompletudeOut(BaseModel):
    id: UUID
    referencia_ano: int
    referencia_mes: int
    municipio_id: Optional[str] = None
    municipio_nome: Optional[str] = None
    total_observado: int
    status: str
    criado_em: datetime


class AlertaStatusUpdate(BaseModel):
    status: Literal["ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"]


class PaginatedAlertas(BaseModel):
    items: list[AlertaCompletudeOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    totais_por_status: dict[str, int]
    municipios_afetados: int


class ResultadoVarredura(BaseModel):
    alertas_criados: int
    alertas_atualizados: int
    municipios_analisados: int
    meses_analisados: int
```

`totais_por_status` e `municipios_afetados` alimentam a faixa de KPIs da tela numa única
chamada, em vez de quatro requisições — são calculados no endpoint da Task 3.

- [ ] **Step 4: Criar o pacote de serviços**

```bash
touch backend/app/services/__init__.py
```

O arquivo fica vazio (é só o marcador de pacote).

- [ ] **Step 5: Implementar o serviço**

Crie `backend/app/services/completude.py`:

```python
"""RF15 - Detecção de meses/municípios com volume de registros fora do padrão.

A faixa esperada de cada município vem do histórico dele mesmo:
`limite_inferior = média - k * desvio_padrão` sobre os totais mensais. Só o lado
inferior gera alerta — o requisito trata de dado faltando, e um pico acima da
média é mutirão de vacinação, não falha de completude.

A agregação por (município, ano, mês) acontece no banco, reduzindo milhões de
registros a alguns milhares de linhas; média e desvio são calculados em Python
porque o SQLite (usado nos testes) não tem `stddev`, e o mesmo código precisa
rodar em PostgreSQL na produção.
"""

from collections import defaultdict
from statistics import mean, pstdev

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AlertaCompletude, RegistroVacinacao
from app.schemas import ResultadoVarredura

K_PADRAO = 2.0
MINIMO_MESES = 3


def _totais_mensais(db: Session) -> dict[str, dict[tuple[int, int], int]]:
    """{municipio_id: {(ano, mes): total_de_doses}} para os registros ativos.

    Agrupa pelo município de aplicação. Todos os `status_dado` entram: completude
    mede volume de coleta, não validade do dado.
    """
    ano = func.extract("year", RegistroVacinacao.data_vacinacao)
    mes = func.extract("month", RegistroVacinacao.data_vacinacao)
    linhas = (
        db.query(
            RegistroVacinacao.municipio_vacina_id.label("municipio_id"),
            ano.label("ano"),
            mes.label("mes"),
            func.sum(RegistroVacinacao.quantidade).label("total"),
        )
        .filter(RegistroVacinacao.ativo.is_(True))
        .group_by(RegistroVacinacao.municipio_vacina_id, ano, mes)
        .all()
    )

    series: dict[str, dict[tuple[int, int], int]] = defaultdict(dict)
    for linha in linhas:
        series[linha.municipio_id][(int(linha.ano), int(linha.mes))] = int(linha.total)
    return series


def _preencher_meses_ausentes(serie: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    """Completa com zero os meses sem nenhum registro dentro do intervalo coberto.

    Um mês que sumiu da base é justamente o caso que o RF15 precisa apontar; sem
    isso ele nem entraria na série e passaria despercebido.
    """
    chaves = sorted(serie)
    primeiro = chaves[0][0] * 12 + (chaves[0][1] - 1)
    ultimo = chaves[-1][0] * 12 + (chaves[-1][1] - 1)

    completa: dict[tuple[int, int], int] = {}
    for indice in range(primeiro, ultimo + 1):
        chave = (indice // 12, indice % 12 + 1)
        completa[chave] = serie.get(chave, 0)
    return completa


def _upsert_alerta(db: Session, ano: int, mes: int, municipio_id: str, total: int) -> bool:
    """Grava o alerta e devolve True se foi criado agora.

    Um alerta já existente tem apenas o total atualizado: o `status` definido pelo
    administrador (RF16) é preservado, senão cada varredura apagaria a triagem.
    """
    alerta = (
        db.query(AlertaCompletude)
        .filter(
            AlertaCompletude.referencia_ano == ano,
            AlertaCompletude.referencia_mes == mes,
            AlertaCompletude.municipio_id == municipio_id,
        )
        .first()
    )
    if alerta is not None:
        alerta.total_observado = total
        return False

    db.add(
        AlertaCompletude(
            referencia_ano=ano,
            referencia_mes=mes,
            municipio_id=municipio_id,
            total_observado=total,
            status="ABERTO",
        )
    )
    return True


def detectar_anomalias(
    db: Session, k: float = K_PADRAO, minimo_meses: int = MINIMO_MESES
) -> ResultadoVarredura:
    """Varre o histórico mensal de cada município e registra os meses anômalos."""
    criados = 0
    atualizados = 0
    municipios_analisados = 0
    meses_analisados = 0

    for municipio_id, serie in _totais_mensais(db).items():
        if len(serie) < minimo_meses:
            # Dois pontos não definem faixa nenhuma: alertar aqui só produziria
            # falso positivo para todo município pequeno ou recém-cadastrado.
            continue

        completa = _preencher_meses_ausentes(serie)
        municipios_analisados += 1
        meses_analisados += len(completa)

        totais = list(completa.values())
        limite_inferior = mean(totais) - k * pstdev(totais)

        for (ano, mes), total in completa.items():
            if total >= limite_inferior:
                continue
            if _upsert_alerta(db, ano, mes, municipio_id, total):
                criados += 1
            else:
                atualizados += 1

    db.commit()
    return ResultadoVarredura(
        alertas_criados=criados,
        alertas_atualizados=atualizados,
        municipios_analisados=municipios_analisados,
        meses_analisados=meses_analisados,
    )
```

- [ ] **Step 6: Rodar os testes e conferir que passam**

Run: `python -m pytest backend/tests/test_completude.py -v --no-cov`
Expected: 6 passed

- [ ] **Step 7: Conferir a cobertura da suíte inteira**

Run: `python -m pytest -q`
Expected: todos os testes passam e a cobertura fecha em 100%. Se alguma linha de
`app/services/completude.py` aparecer em `Missing`, acrescente o teste que falta antes de commitar.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services backend/app/schemas.py backend/tests/test_completude.py
git commit -m "feat: RF15 servico de deteccao de anomalias de completude"
```

---

### Task 2: Endpoint de varredura `POST /completude/recalcular` (RF15)

**Files:**

- Create: `backend/app/routers/completude.py`
- Modify: `backend/app/main.py` (lista `OPENAPI_TAGS` e bloco de `include_router`)
- Test: `backend/tests/test_completude.py` (acrescentar ao arquivo da Task 1)

**Interfaces:**

- Consumes: `detectar_anomalias` (Task 1), `ResultadoVarredura` (Task 1), `get_admin_only` de `app.dependencies`.
- Produces: `router` com prefix `/completude`; constante `STATUS_VALIDOS`.

- [ ] **Step 1: Escrever os testes (falhando)**

Acrescente no topo de `backend/tests/test_completude.py` os imports e helpers de autenticação (mesmo padrão de `backend/tests/test_fluxo.py`):

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import UsuarioAdmin
from app.security import get_password_hash

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
```

E os testes do endpoint, no fim do arquivo:

```python
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
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `python -m pytest backend/tests/test_completude.py -k recalcular -v --no-cov`
Expected: FAIL com 404 (a rota ainda não existe)

- [ ] **Step 3: Criar o router com o endpoint de varredura**

Crie `backend/app/routers/completude.py`:

```python
"""RF15 (varredura de completude) e RF16 (gestão de status dos alertas)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_only
from app.schemas import ResultadoVarredura
from app.services.completude import K_PADRAO, detectar_anomalias

router = APIRouter(prefix="/completude", tags=["Completude"])

STATUS_VALIDOS = ("ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO")
PAGE_SIZE_PADRAO = 10
PAGE_SIZE_MAXIMO = 100


@router.post(
    "/recalcular",
    response_model=ResultadoVarredura,
    summary="Executa a varredura de completude e grava os alertas",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Operação restrita ao perfil Administrador."},
    },
)
def recalcular_completude(
    k: float = K_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_only),
):
    """RF15 - Recalcula o volume mensal por município, compara com a faixa
    esperada (média - k·desvio) e registra em `alertas_completude` os meses fora
    do padrão. Alertas já existentes têm o total atualizado e o status
    preservado."""
    return detectar_anomalias(db, k=k)
```

- [ ] **Step 4: Registrar o router em `main.py`**

Em `backend/app/main.py`, acrescente o import junto dos outros routers:

```python
from app.routers.completude import router as completude_router
```

a tag no fim da lista `OPENAPI_TAGS`:

```python
    {
        "name": "Completude",
        "description": (
            "Alertas de completude de dados: varredura automática de meses/municípios "
            "fora do padrão e gestão do status dos alertas (perfil ADMIN para escrita)."
        ),
    },
```

e a inclusão junto das outras:

```python
app.include_router(completude_router)
```

- [ ] **Step 5: Rodar os testes e conferir que passam**

Run: `python -m pytest backend/tests/test_completude.py -k recalcular -v --no-cov`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/completude.py backend/app/main.py backend/tests/test_completude.py
git commit -m "feat: RF15 endpoint POST /completude/recalcular restrito a admin"
```

---

### Task 3: Listagem `GET /completude/alertas` (RF16)

**Files:**

- Modify: `backend/app/routers/completude.py`
- Test: `backend/tests/test_completude.py`

**Interfaces:**

- Consumes: `PaginatedAlertas`, `AlertaCompletudeOut` (Task 1), `STATUS_VALIDOS` (Task 2), `get_current_user` e `validate_municipio_scope` de `app.dependencies`.
- Produces: `GET /completude/alertas` respondendo `PaginatedAlertas`; helper `_alerta_out(alerta) -> AlertaCompletudeOut`.

- [ ] **Step 1: Escrever os testes (falhando)**

Acrescente em `backend/tests/test_completude.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `python -m pytest backend/tests/test_completude.py -k listar -v --no-cov`
Expected: FAIL com 404

- [ ] **Step 3: Implementar o endpoint**

Em `backend/app/routers/completude.py`, acrescente aos imports:

```python
from math import ceil
from typing import Optional

from app.dependencies import get_admin_only, get_current_user, validate_municipio_scope
from app.models import AlertaCompletude
from app.schemas import AlertaCompletudeOut, PaginatedAlertas, ResultadoVarredura
from sqlalchemy import func
```

e depois do endpoint de varredura:

```python
def _alerta_out(alerta: AlertaCompletude) -> AlertaCompletudeOut:
    """Serializa o alerta já com o nome do município resolvido pelo relationship."""
    return AlertaCompletudeOut(
        id=alerta.id,
        referencia_ano=alerta.referencia_ano,
        referencia_mes=alerta.referencia_mes,
        municipio_id=alerta.municipio_id,
        municipio_nome=alerta.municipio.nome if alerta.municipio else None,
        total_observado=alerta.total_observado,
        status=alerta.status,
        criado_em=alerta.criado_em,
    )


@router.get(
    "/alertas",
    response_model=PaginatedAlertas,
    summary="Lista os alertas de completude, com filtro por status",
    responses={401: {"description": "Token ausente ou inválido."}},
)
def listar_alertas(
    status: Optional[str] = None,
    municipio_id: Optional[str] = None,
    ano: Optional[int] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE_PADRAO,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """RF16 - Lista os alertas gerados pela varredura, do mês mais recente para o
    mais antigo, com filtros opcionais por status, município e ano.

    Gestores municipais enxergam apenas o município ao qual estão vinculados. Os
    contadores de KPI (`totais_por_status`, `municipios_afetados`) desconsideram o
    filtro de status, para a tela mostrar a distribuição completa do recorte."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = PAGE_SIZE_PADRAO
    if page_size > PAGE_SIZE_MAXIMO:
        page_size = PAGE_SIZE_MAXIMO

    if current_user.role == "GESTOR_MUNICIPAL":
        validate_municipio_scope(current_user, municipio_id)
        municipio_id = current_user.municipio_alocado_id

    # Filtros de recorte (sem o status): valem para a listagem e para os KPIs.
    base = db.query(AlertaCompletude)
    if municipio_id:
        base = base.filter(AlertaCompletude.municipio_id == municipio_id)
    if ano:
        base = base.filter(AlertaCompletude.referencia_ano == ano)

    contagens = dict(
        base.with_entities(AlertaCompletude.status, func.count(AlertaCompletude.id))
        .group_by(AlertaCompletude.status)
        .all()
    )
    totais_por_status = {chave: int(contagens.get(chave, 0)) for chave in STATUS_VALIDOS}
    municipios_afetados = base.with_entities(
        func.count(func.distinct(AlertaCompletude.municipio_id))
    ).scalar()

    query = base
    if status:
        query = query.filter(AlertaCompletude.status == status)

    total = query.count()
    total_pages = ceil(total / page_size) if total else 0
    linhas = (
        query.order_by(
            AlertaCompletude.referencia_ano.desc(),
            AlertaCompletude.referencia_mes.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedAlertas(
        items=[_alerta_out(alerta) for alerta in linhas],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        totais_por_status=totais_por_status,
        municipios_afetados=int(municipios_afetados or 0),
    )
```

- [ ] **Step 4: Rodar os testes e conferir que passam**

Run: `python -m pytest backend/tests/test_completude.py -v --no-cov`
Expected: todos passam

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/completude.py backend/tests/test_completude.py
git commit -m "feat: RF16 listagem paginada de alertas de completude com filtros"
```

---

### Task 4: Mudança de status `PUT /completude/alertas/{id}` (RF16)

**Files:**

- Modify: `backend/app/routers/completude.py`
- Test: `backend/tests/test_completude.py`

**Interfaces:**

- Consumes: `AlertaStatusUpdate` (Task 1), `_alerta_out` (Task 3), `get_admin_only`.
- Produces: `PUT /completude/alertas/{alerta_id}` respondendo `AlertaCompletudeOut`.

- [ ] **Step 1: Escrever os testes (falhando)**

Acrescente em `backend/tests/test_completude.py`:

```python
import pytest


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
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `python -m pytest backend/tests/test_completude.py -k status -v --no-cov`
Expected: FAIL com 405/404 (a rota ainda não existe)

- [ ] **Step 3: Implementar o endpoint**

Em `backend/app/routers/completude.py`, acrescente aos imports:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from app.schemas import AlertaCompletudeOut, AlertaStatusUpdate, PaginatedAlertas, ResultadoVarredura
```

e no fim do arquivo:

```python
@router.put(
    "/alertas/{alerta_id}",
    response_model=AlertaCompletudeOut,
    summary="Altera o status de um alerta de completude",
    responses={
        401: {"description": "Token ausente ou inválido."},
        403: {"description": "Operação restrita ao perfil Administrador."},
        404: {"description": "Alerta de completude não encontrado."},
    },
)
def atualizar_status_alerta(
    alerta_id: UUID,
    payload: AlertaStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_admin_only),
):
    """RF16 - Move o alerta para `INVESTIGANDO`, `RESOLVIDO` ou `FALSO_POSITIVO`.
    Restrito ao perfil Administrador."""
    alerta = db.query(AlertaCompletude).filter(AlertaCompletude.id == alerta_id).first()
    if alerta is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Alerta de completude não encontrado.",
        )

    alerta.status = payload.status
    db.commit()
    db.refresh(alerta)
    return _alerta_out(alerta)
```

- [ ] **Step 4: Rodar os testes e conferir que passam**

Run: `python -m pytest backend/tests/test_completude.py -v --no-cov`
Expected: todos passam

- [ ] **Step 5: Rodar a suíte completa com cobertura**

Run: `python -m pytest -q`
Expected: todos passam, cobertura 100%. Nenhuma linha de `app/routers/completude.py` ou
`app/services/completude.py` pode aparecer em `Missing`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/completude.py backend/tests/test_completude.py
git commit -m "feat: RF16 PUT de status do alerta restrito a admin"
```

---

### Task 5: Cliente HTTP e cache do frontend

**Files:**

- Modify: `frontend/api_client.py` (acrescentar no fim)
- Modify: `frontend/data_cache.py`
- Test: `frontend/tests/test_completude_api.py` (novo)

**Interfaces:**

- Consumes: `_request` de `api_client` (já existente).
- Produces:
  - `listar_alertas_completude(token, status=None, municipio_id=None, ano=None, page=1, page_size=10) -> dict`
  - `atualizar_status_alerta(token, alerta_id, novo_status) -> dict`
  - `recalcular_completude(token, k=2.0) -> dict`
  - `data_cache.alertas_completude(...)` — mesma assinatura de `listar_alertas_completude`, com cache.

- [ ] **Step 1: Escrever os testes (falhando)**

Crie `frontend/tests/test_completude_api.py`:

```python
from unittest.mock import patch

from api_client import atualizar_status_alerta, listar_alertas_completude, recalcular_completude


@patch("api_client._request")
def test_listar_alertas_envia_apenas_os_filtros_preenchidos(mock_request):
    mock_request.return_value = {"items": []}

    listar_alertas_completude("tk", status="ABERTO", page=2, page_size=25)

    _, kwargs = mock_request.call_args
    assert kwargs["params"] == {"page": 2, "page_size": 25, "status": "ABERTO"}


@patch("api_client._request")
def test_listar_alertas_com_todos_os_filtros(mock_request):
    mock_request.return_value = {"items": []}

    listar_alertas_completude("tk", status="RESOLVIDO", municipio_id="2304400", ano=2024)

    _, kwargs = mock_request.call_args
    assert kwargs["params"]["municipio_id"] == "2304400"
    assert kwargs["params"]["ano"] == 2024


@patch("api_client._request")
def test_atualizar_status_usa_put_no_alerta(mock_request):
    mock_request.return_value = {"status": "RESOLVIDO"}

    atualizar_status_alerta("tk", "abc-123", "RESOLVIDO")

    args, kwargs = mock_request.call_args
    assert args[0] == "PUT"
    assert args[1] == "/completude/alertas/abc-123"
    assert kwargs["json"] == {"status": "RESOLVIDO"}


@patch("api_client._request")
def test_recalcular_envia_o_k(mock_request):
    mock_request.return_value = {"alertas_criados": 0}

    recalcular_completude("tk", k=3.0)

    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert kwargs["params"] == {"k": 3.0}
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `cd frontend && python -m pytest tests/test_completude_api.py -v --no-cov`
Expected: FAIL com `ImportError: cannot import name 'listar_alertas_completude'`

- [ ] **Step 3: Implementar as funções do cliente**

No fim de `frontend/api_client.py`:

```python
# --- COMPLETUDE (RF15 & RF16) ---


def listar_alertas_completude(
    token: str,
    status: Optional[str] = None,
    municipio_id: Optional[str] = None,
    ano: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    if municipio_id:
        params["municipio_id"] = municipio_id
    if ano:
        params["ano"] = ano
    return _request("GET", "/completude/alertas", token, params=params)


def atualizar_status_alerta(token: str, alerta_id: str, novo_status: str) -> dict:
    return _request(
        "PUT", f"/completude/alertas/{alerta_id}", token, json={"status": novo_status}
    )


def recalcular_completude(token: str, k: float = 2.0) -> dict:
    return _request("POST", "/completude/recalcular", token, params={"k": k})
```

- [ ] **Step 4: Acrescentar o wrapper com cache**

Em `frontend/data_cache.py`, acrescente `listar_alertas_completude` ao import de `api_client` e, no fim do arquivo:

```python
@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def alertas_completude(
    token: str,
    status=None,
    municipio_id=None,
    ano=None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Listagem de alertas com o mesmo TTL dos demais agregados: a varredura e a
    troca de status limpam o cache explicitamente, então 5 minutos aqui só evita
    repetir a consulta a cada rerun do Streamlit."""
    return listar_alertas_completude(
        token,
        status=status,
        municipio_id=municipio_id,
        ano=ano,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 5: Rodar os testes e conferir que passam**

Run: `cd frontend && python -m pytest tests/test_completude_api.py -v --no-cov`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/api_client.py frontend/data_cache.py frontend/tests/test_completude_api.py
git commit -m "feat: cliente HTTP e cache dos alertas de completude"
```

---

### Task 6: Tela de alertas (leitura) e navegação

**Files:**

- Create: `frontend/completude_ui.py`
- Modify: `frontend/theme.py` (dicionário `BADGE_TONES`, linha 22)
- Modify: `frontend/app.py` (dicionário `PAGINAS` e roteamento no fim do arquivo)
- Test: `frontend/tests/test_completude_ui.py` (novo)

**Interfaces:**

- Consumes: `data_cache.alertas_completude`, `data_cache.listar_municipios_resumido`, `api_client.ApiError`, `theme.badge_html`.
- Produces: `render_completude_section()`; constantes `STATUS_ROTULOS`, `OPCOES_STATUS`, `PAGE_SIZE`.

- [ ] **Step 1: Escrever os testes (falhando)**

Crie `frontend/tests/test_completude_ui.py`:

```python
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from api_client import ApiError

_MUNICIPIOS = [("2304400", "Fortaleza"), ("2303709", "Caucaia")]


def _pagina_alertas(status="ABERTO"):
    return {
        "items": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "referencia_ano": 2024,
                "referencia_mes": 9,
                "municipio_id": "2304400",
                "municipio_nome": "Fortaleza",
                "total_observado": 10,
                "status": status,
                "criado_em": "2026-08-20T10:00:00",
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 10,
        "total_pages": 1,
        "totais_por_status": {
            "ABERTO": 1,
            "INVESTIGANDO": 0,
            "RESOLVIDO": 0,
            "FALSO_POSITIVO": 0,
        },
        "municipios_afetados": 1,
    }


def _abrir(role="ADMIN", municipio_id=None):
    at = AppTest.from_file("app.py")
    at.session_state["token"] = "faketoken"
    at.session_state["role"] = role
    at.session_state["municipio_id"] = municipio_id
    at.session_state["pagina_ativa"] = "completude"
    return at


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_tela_lista_os_alertas(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert mock_alertas.called
    textos = " ".join(m.value or "" for m in at.markdown)
    assert "Alertas de Completude" in textos
    assert "Fortaleza" in textos
    assert "09/2024" in textos


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_tela_mostra_os_kpis(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    rotulos = [m.label for m in at.metric]
    assert "Total de alertas" in rotulos
    assert "Municípios afetados" in rotulos


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_filtro_de_status_e_repassado_a_api(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas("RESOLVIDO")
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.selectbox(key="completude_status").select("Resolvido").run()

    assert not at.exception
    assert mock_alertas.call_args.kwargs["status"] == "RESOLVIDO"


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_filtro_de_municipio_e_ano_sao_repassados(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.selectbox(key="completude_municipio").select("Fortaleza (2304400)").run()
    at.number_input(key="completude_ano").set_value(2024).run()

    assert not at.exception
    assert mock_alertas.call_args.kwargs["municipio_id"] == "2304400"
    assert mock_alertas.call_args.kwargs["ano"] == 2024


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_lista_vazia_mostra_aviso(mock_alertas, mock_municipios):
    vazio = _pagina_alertas()
    vazio["items"] = []
    vazio["total"] = 0
    vazio["total_pages"] = 0
    vazio["municipios_afetados"] = 0
    vazio["totais_por_status"] = {
        "ABERTO": 0,
        "INVESTIGANDO": 0,
        "RESOLVIDO": 0,
        "FALSO_POSITIVO": 0,
    }
    mock_alertas.return_value = vazio
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Nenhum alerta" in (i.value or "") for i in at.info)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_da_api_exibe_mensagem(mock_alertas, mock_municipios):
    mock_alertas.side_effect = ApiError("Servidor indisponível.")
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()

    assert not at.exception
    assert any("Servidor indisponível." in (e.value or "") for e in at.error)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_ao_carregar_municipios_nao_quebra_a_tela(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.side_effect = ApiError("Servidor indisponível.")

    at = _abrir().run()

    assert not at.exception
    assert mock_alertas.called


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_gestor_municipal_nao_ve_acoes_de_admin(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir(role="GESTOR_MUNICIPAL", municipio_id="2304400").run()

    assert not at.exception
    chaves = [b.key for b in at.button]
    assert "completude_varredura" not in chaves


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_paginacao_avanca_e_volta(mock_alertas, mock_municipios):
    pagina = _pagina_alertas()
    pagina["total"] = 25
    pagina["total_pages"] = 3
    mock_alertas.return_value = pagina
    mock_municipios.return_value = _MUNICIPIOS

    at = _abrir().run()
    at.button(key="completude_proxima").click().run()
    assert mock_alertas.call_args.kwargs["page"] == 2

    at.button(key="completude_anterior").click().run()
    assert mock_alertas.call_args.kwargs["page"] == 1


def test_tela_sem_token_avisa():
    at = AppTest.from_file("app.py")
    at.session_state["token"] = None
    at.run()

    assert not at.exception
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `cd frontend && python -m pytest tests/test_completude_ui.py -v --no-cov`
Expected: FAIL com `ModuleNotFoundError: No module named 'completude_ui'`

- [ ] **Step 3: Acrescentar o tom vermelho ao tema**

Em `frontend/theme.py`, no dicionário `BADGE_TONES` (linha 22), acrescente a entrada:

```python
    "danger": ("#fee2e2", "#b91c1c"),
```

- [ ] **Step 4: Criar a tela (somente leitura)**

Crie `frontend/completude_ui.py`:

```python
"""RF15/RF16 - Alertas de completude de dados.

Lista os meses/municípios que a varredura apontou como fora do padrão esperado e
permite ao administrador tratar cada alerta. A varredura em si roda no backend
(POST /completude/recalcular); esta tela apenas a dispara e mostra o resultado.
"""

import streamlit as st

from api_client import ApiError
from data_cache import alertas_completude, listar_municipios_resumido
from theme import badge_html

# Rótulo exibido e tom do badge de cada status do banco.
STATUS_ROTULOS = {
    "ABERTO": ("Aberto", "danger"),
    "INVESTIGANDO": ("Investigando", "warning"),
    "RESOLVIDO": ("Resolvido", "success"),
    "FALSO_POSITIVO": ("Falso positivo", "neutral"),
}
OPCOES_STATUS = ["Todos"] + [rotulo for rotulo, _ in STATUS_ROTULOS.values()]
_ROTULO_PARA_STATUS = {rotulo: chave for chave, (rotulo, _) in STATUS_ROTULOS.items()}
PAGE_SIZE = 10


def _init_state():
    if "completude_page" not in st.session_state:
        st.session_state["completude_page"] = 1


def _municipios(token):
    try:
        return listar_municipios_resumido(token)
    except ApiError:
        # A tela continua útil sem o seletor de município.
        return []


def _render_filtros(municipios):
    col_status, col_municipio, col_ano = st.columns([1.2, 2, 1])

    with col_status:
        rotulo = st.selectbox("Status", OPCOES_STATUS, key="completude_status")
        status = _ROTULO_PARA_STATUS.get(rotulo)

    with col_municipio:
        opcoes = ["Todos"] + [f"{nome} ({mid})" for mid, nome in municipios]
        escolha = st.selectbox("Município", opcoes, key="completude_municipio")
        municipio_id = None
        if escolha != "Todos":
            municipio_id = escolha.split("(")[-1].replace(")", "").strip()

    with col_ano:
        ano = st.number_input(
            "Ano", min_value=0, max_value=2100, value=0, step=1, key="completude_ano"
        )
        ano = int(ano) or None

    return status, municipio_id, ano


def _render_kpis(pagina):
    totais = pagina["totais_por_status"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de alertas", pagina["total"])
    col2.metric("Abertos", totais["ABERTO"])
    col3.metric("Em investigação", totais["INVESTIGANDO"])
    col4.metric("Municípios afetados", pagina["municipios_afetados"])


def _render_linha(alerta):
    colunas = st.columns([1.2, 2.4, 1.4, 1.6, 2.4])
    colunas[0].markdown(f"{alerta['referencia_mes']:02d}/{alerta['referencia_ano']}")
    colunas[1].markdown(alerta.get("municipio_nome") or "—")
    colunas[2].markdown(f"{alerta['total_observado']}")
    rotulo, tom = STATUS_ROTULOS.get(alerta["status"], (alerta["status"], "neutral"))
    colunas[3].markdown(badge_html(rotulo, tom), unsafe_allow_html=True)
    return colunas[4]


def _render_paginacao(pagina):
    total_paginas = max(pagina["total_pages"], 1)
    atual = st.session_state["completude_page"]
    col_info, _, col_anterior, col_proxima = st.columns([6, 3, 0.6, 0.6])
    col_info.caption(f"Página {atual} de {total_paginas} — {pagina['total']} alertas")

    if col_anterior.button("◀", key="completude_anterior", disabled=atual <= 1):
        st.session_state["completude_page"] = atual - 1
        st.rerun()
    if col_proxima.button("▶", key="completude_proxima", disabled=atual >= total_paginas):
        st.session_state["completude_page"] = atual + 1
        st.rerun()


def render_completude_section():
    """RF15/RF16 - Painel de alertas de completude."""
    token = st.session_state.get("token")
    if not token:
        st.warning("É necessário estar autenticado para visualizar os alertas.")
        return

    _init_state()

    st.markdown(
        '<div class="page-title">⚠️ Alertas de Completude</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="page-subtitle">Meses e municípios com volume de registros fora '
        "da faixa esperada.</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        status, municipio_id, ano = _render_filtros(_municipios(token))

    try:
        pagina = alertas_completude(
            token,
            status=status,
            municipio_id=municipio_id,
            ano=ano,
            page=st.session_state["completude_page"],
            page_size=PAGE_SIZE,
        )
    except ApiError as exc:
        st.error(f"Erro ao carregar os alertas de completude: {exc.message}")
        return

    _render_kpis(pagina)

    if not pagina["items"]:
        st.info("Nenhum alerta de completude para os filtros selecionados.")
        return

    st.markdown("<hr>", unsafe_allow_html=True)
    cabecalho = st.columns([1.2, 2.4, 1.4, 1.6, 2.4])
    for coluna, titulo in zip(
        cabecalho, ["Referência", "Município", "Doses", "Status", ""]
    ):
        coluna.markdown(f"**{titulo}**")
    st.markdown("<hr>", unsafe_allow_html=True)

    for alerta in pagina["items"]:
        _render_linha(alerta)

    _render_paginacao(pagina)
```

- [ ] **Step 5: Ligar a tela na navegação**

Em `frontend/app.py`, no dicionário `PAGINAS`, acrescente a entrada depois de `fluxo`:

```python
        "completude": "⚠️ Alertas de Completude",
```

acrescente o import junto dos demais no topo do arquivo:

```python
from completude_ui import render_completude_section
```

e o ramo no roteamento do fim do arquivo, antes do `elif` de `municipios`:

```python
    elif st.session_state["pagina_ativa"] == "completude":
        render_completude_section()
```

- [ ] **Step 6: Rodar os testes e conferir que passam**

Run: `cd frontend && python -m pytest tests/test_completude_ui.py -v --no-cov`
Expected: todos passam

- [ ] **Step 7: Rodar a suíte do frontend inteira**

Run: `cd frontend && python -m pytest -q`
Expected: todos passam e a cobertura fecha em 100%. Se alguma linha de `completude_ui.py`
aparecer em `Missing`, acrescente o teste que falta antes de commitar.

- [ ] **Step 8: Commit**

```bash
git add frontend/completude_ui.py frontend/theme.py frontend/app.py frontend/tests/test_completude_ui.py
git commit -m "feat: RF16 tela de alertas de completude e item de navegacao"
```

---

### Task 7: Ações de administrador na tela (RF15 + RF16)

**Files:**

- Modify: `frontend/completude_ui.py`
- Test: `frontend/tests/test_completude_ui.py`

**Interfaces:**

- Consumes: `api_client.atualizar_status_alerta`, `api_client.recalcular_completude` (Task 5); `render_completude_section` (Task 6).
- Produces: botão `completude_varredura`; por linha, `completude_status_<id>` (selectbox) e `completude_salvar_<id>` (botão).

- [ ] **Step 1: Escrever os testes (falhando)**

Acrescente em `frontend/tests/test_completude_ui.py`:

```python
@patch("completude_ui.recalcular_completude")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_admin_dispara_a_varredura(mock_alertas, mock_municipios, mock_recalcular):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_recalcular.return_value = {
        "alertas_criados": 2,
        "alertas_atualizados": 1,
        "municipios_analisados": 5,
        "meses_analisados": 60,
    }

    at = _abrir().run()
    at.button(key="completude_varredura").click().run()

    assert not at.exception
    assert mock_recalcular.called
    assert any("2" in (s.value or "") for s in at.success)


@patch("completude_ui.recalcular_completude")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_na_varredura_exibe_mensagem(mock_alertas, mock_municipios, mock_recalcular):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_recalcular.side_effect = ApiError("Operação não permitida para o seu perfil de acesso.")

    at = _abrir().run()
    at.button(key="completude_varredura").click().run()

    assert not at.exception
    assert any("não permitida" in (e.value or "") for e in at.error)


@patch("completude_ui.atualizar_status_alerta")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_admin_altera_o_status_de_um_alerta(mock_alertas, mock_municipios, mock_atualizar):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_atualizar.return_value = {"status": "INVESTIGANDO"}
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir().run()
    at.selectbox(key=f"completude_status_{alerta_id}").select("Investigando").run()
    at.button(key=f"completude_salvar_{alerta_id}").click().run()

    assert not at.exception
    assert mock_atualizar.call_args.args[1] == alerta_id
    assert mock_atualizar.call_args.args[2] == "INVESTIGANDO"


@patch("completude_ui.atualizar_status_alerta")
@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_erro_ao_salvar_status_exibe_mensagem(mock_alertas, mock_municipios, mock_atualizar):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    mock_atualizar.side_effect = ApiError("Alerta de completude não encontrado.")
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir().run()
    at.button(key=f"completude_salvar_{alerta_id}").click().run()

    assert not at.exception
    assert any("não encontrado" in (e.value or "") for e in at.error)


@patch("completude_ui.listar_municipios_resumido")
@patch("completude_ui.alertas_completude")
def test_gestor_estadual_ve_a_lista_sem_seletor_de_status(mock_alertas, mock_municipios):
    mock_alertas.return_value = _pagina_alertas()
    mock_municipios.return_value = _MUNICIPIOS
    alerta_id = "11111111-1111-1111-1111-111111111111"

    at = _abrir(role="GESTOR_ESTADUAL").run()

    assert not at.exception
    chaves = [s.key for s in at.selectbox]
    assert f"completude_status_{alerta_id}" not in chaves
```

- [ ] **Step 2: Rodar os testes e conferir que falham**

Run: `cd frontend && python -m pytest tests/test_completude_ui.py -k "varredura or status_de_um" -v --no-cov`
Expected: FAIL — `completude_ui` não tem `recalcular_completude`, e a chave de botão não existe

- [ ] **Step 3: Implementar as ações**

Em `frontend/completude_ui.py`, troque o import de `api_client` por:

```python
from api_client import ApiError, atualizar_status_alerta, recalcular_completude
```

acrescente as duas funções antes de `render_completude_section`:

```python
def _render_botao_varredura(token):
    """RF15 - dispara a varredura no backend e limpa o cache da listagem."""
    if not st.button("Executar varredura", type="primary", key="completude_varredura"):
        return
    try:
        resultado = recalcular_completude(token)
    except ApiError as exc:
        st.error(f"Erro ao executar a varredura: {exc.message}")
        return
    st.cache_data.clear()
    st.success(
        f"Varredura concluída: {resultado['alertas_criados']} alerta(s) criado(s) e "
        f"{resultado['alertas_atualizados']} atualizado(s) em "
        f"{resultado['municipios_analisados']} município(s)."
    )


def _render_acao_status(coluna, token, alerta):
    """RF16 - seletor de status + gravação, só para o perfil Administrador."""
    rotulos = [rotulo for rotulo, _ in STATUS_ROTULOS.values()]
    atual = STATUS_ROTULOS.get(alerta["status"], ("Aberto", "danger"))[0]
    col_select, col_salvar = coluna.columns([2, 1])
    escolha = col_select.selectbox(
        "Status",
        rotulos,
        index=rotulos.index(atual),
        key=f"completude_status_{alerta['id']}",
        label_visibility="collapsed",
    )
    if not col_salvar.button("Salvar", key=f"completude_salvar_{alerta['id']}"):
        return
    try:
        atualizar_status_alerta(token, alerta["id"], _ROTULO_PARA_STATUS[escolha])
    except ApiError as exc:
        st.error(f"Erro ao atualizar o alerta: {exc.message}")
        return
    st.cache_data.clear()
    st.rerun()
```

Em `render_completude_section`, guarde o perfil logo depois de `_init_state()`:

```python
    e_admin = st.session_state.get("role") == "ADMIN"
```

chame o botão de varredura logo depois do subtítulo:

```python
    if e_admin:
        _render_botao_varredura(token)
```

e, no laço que renderiza as linhas, use a coluna devolvida por `_render_linha`:

```python
    for alerta in pagina["items"]:
        coluna_acao = _render_linha(alerta)
        if e_admin:
            _render_acao_status(coluna_acao, token, alerta)
```

- [ ] **Step 4: Rodar os testes e conferir que passam**

Run: `cd frontend && python -m pytest tests/test_completude_ui.py -v --no-cov`
Expected: todos passam

- [ ] **Step 5: Rodar as duas suítes completas**

Run: `python -m pytest -q`
Expected: backend 100% de cobertura, todos passam

Run: `cd frontend && python -m pytest -q`
Expected: frontend 100% de cobertura, todos passam

- [ ] **Step 6: Conferir o formatador do CI**

Run: `npx prettier --check "**/*.{json,md,yml,yaml}"`
Expected: "All matched files use Prettier code style!". Se algum arquivo aparecer,
rode `npx prettier --write` nele e inclua no commit.

- [ ] **Step 7: Commit**

```bash
git add frontend/completude_ui.py frontend/tests/test_completude_ui.py
git commit -m "feat: RF15/RF16 acoes de varredura e mudanca de status para admin"
```

---

## Verificação final

Depois da Task 7, com o backend e o frontend rodando (`docker compose up` ou os
processos locais), confira na tela:

1. Entrar como `admin@imunizacao.local` e abrir "⚠️ Alertas de Completude" no menu.
2. Clicar em "Executar varredura" e ver a mensagem com os contadores.
3. Filtrar por "Aberto" e confirmar que a lista responde ao filtro.
4. Mudar um alerta para "Investigando", salvar, e conferir que o badge muda.
5. Entrar com um gestor municipal e confirmar que a tela abre somente leitura, com
   apenas os alertas do município vinculado.
