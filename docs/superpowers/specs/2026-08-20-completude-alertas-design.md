# RF15 & RF16 — Monitoramento de completude e gestão de alertas

Data: 2026-08-20
Branch: `feature/20-21-painel-fluxo`

## Problema

A base de vacinação tem meses em que o volume de registros de um município cai
muito abaixo do padrão histórico (setembro foi o caso identificado na análise
exploratória). Hoje nada no sistema sinaliza isso: um gestor que olhe o
dashboard interpreta a queda como redução real de vacinação, quando pode ser
falha de coleta ou de envio de dados.

O escopo cobre dois requisitos:

- **RF15** — rotina que calcula o volume mensal por município, compara com a
  faixa esperada e grava automaticamente uma linha em `alertas_completude`.
- **RF16** — administrador altera o status dos alertas gerados, e a tela lista
  os alertas com filtro por status.

## O que já existe

A tabela `alertas_completude` e o model `AlertaCompletude`
(`backend/app/models.py:130`) já estão no repositório, criados pela migration
`b6b6414f1b16_schema.py`:

| Coluna            | Tipo         | Observação                                                         |
| ----------------- | ------------ | ------------------------------------------------------------------ |
| `id`              | GUID         | PK                                                                 |
| `referencia_ano`  | SmallInteger | not null                                                           |
| `referencia_mes`  | SmallInteger | not null, CHECK 1..12                                              |
| `municipio_id`    | String(7)    | FK `municipios.id_ibge`, nullable                                  |
| `total_observado` | Integer      | not null                                                           |
| `status`          | String(20)   | default ABERTO, CHECK ABERTO/INVESTIGANDO/RESOLVIDO/FALSO_POSITIVO |
| `criado_em`       | TIMESTAMP    | default now                                                        |

**Nenhuma migration nova é necessária.** O schema atende os dois RFs como está.

Não existe router, schema Pydantic, serviço nem tela de completude — é código
novo em todas as camadas.

## Decisões de projeto

### Regra de anomalia: média ± k·desvio-padrão

Para cada município, a faixa esperada é derivada do próprio histórico mensal
dele: `limite_inferior = média − k·desvio_padrão`, com `k = 2.0` por padrão e
parametrizável na chamada.

Escolhida por ser o critério estatístico clássico, explicável na defesa do
projeto e adaptável ao porte de cada município (um limiar absoluto trataria
Fortaleza e um município de 5 mil habitantes com a mesma régua).

Só o **lado inferior** gera alerta. O RF trata de dados faltando; um pico acima
da média é mutirão de vacinação, não falha de completude.

### Onde o cálculo roda: agrega no banco, estatística em Python

`GROUP BY municipio_vacina_id, extract(year), extract(month)` com
`SUM(quantidade)` reduz os ~4,8 milhões de registros a ~11 mil linhas
(≈184 municípios do Ceará × ~60 meses). Média e desvio são calculados em Python
sobre esse agregado.

O motivo é portabilidade: SQLite não tem `stddev` e o projeto roda em SQLite no
ambiente de testes (`backend/tests/conftest.py`) e em PostgreSQL em produção.
Fazer a estatística em SQL exigiria dois caminhos de código; trazer os
registros crus para o Python carregaria milhões de linhas em memória.
`func.extract` é traduzido pelo SQLAlchemy para os dois dialetos — mesmo
recurso já usado em `backend/app/routers/dashboard.py:56`.

### Reexecução preserva a triagem

A varredura faz upsert por `(referencia_ano, referencia_mes, municipio_id)`:
alerta existente tem `total_observado` atualizado e **mantém** o `status`
definido pelo administrador; mês anômalo inédito entra como `ABERTO`. Sem isso,
cada varredura apagaria o trabalho de triagem do RF16.

### Visibilidade e permissões

| Operação                       | ADMIN | GESTOR_ESTADUAL | GESTOR_MUNICIPAL       |
| ------------------------------ | ----- | --------------- | ---------------------- |
| `GET /completude/alertas`      | todos | todos           | só o município alocado |
| `PUT /completude/alertas/{id}` | sim   | 403             | 403                    |
| `POST /completude/recalcular`  | sim   | 403             | 403                    |

O escopo por município reutiliza `validate_municipio_scope`
(`backend/app/dependencies.py`), e a restrição a administrador reutiliza
`get_admin_only`.

## Arquitetura

```
frontend/completude_ui.py     tela: KPIs, filtros, tabela, ações de ADMIN
        |
frontend/api_client.py        listar / atualizar_status / recalcular
        |  HTTP
backend/app/routers/completude.py    GET, PUT, POST + RBAC + paginação
        |
backend/app/services/completude.py   detectar_anomalias() — regra e upsert
        |
registros_vacinacao  ->  alertas_completude
```

A regra de detecção fica isolada em `services/completude.py`, sem dependência
de FastAPI: é chamável e testável sem HTTP, e o router vira apenas transporte,
validação e permissão.

## Backend

### `backend/app/services/completude.py` (novo)

```python
detectar_anomalias(db, k: float = 2.0, minimo_meses: int = 3) -> ResultadoVarredura
```

1. Agrega `registros_vacinacao` por município de aplicação
   (`municipio_vacina_id`), ano e mês, somando `quantidade`, filtrando
   `ativo = true`. Todos os `status_dado` entram: completude mede volume de
   coleta, não validade do dado.
2. Municípios com menos de `minimo_meses` meses de histórico são ignorados —
   dois pontos não definem faixa e gerariam alerta falso para todo município
   pequeno.
3. Calcula média e desvio-padrão populacional dos totais mensais do município e
   marca como anomalia todo mês com `total < média − k·desvio`.
4. **Meses ausentes** dentro do intervalo coberto pelo histórico do município
   (do primeiro ao último mês com dado) entram na série como `0` e, por
   consequência, como anomalia. É o caso "setembro sumiu da base".
5. Upsert em `alertas_completude` conforme a decisão de reexecução acima.

Retorna `ResultadoVarredura`: `alertas_criados`, `alertas_atualizados`,
`municipios_analisados`, `meses_analisados`.

### `backend/app/routers/completude.py` (novo)

Prefix `/completude`, tag `"Completude"` registrada em `OPENAPI_TAGS`
(`backend/app/main.py`) e router incluído via `app.include_router`.

**`POST /completude/recalcular`** — query param opcional `k` (padrão 2.0).
Dependência `get_admin_only`. Responde `ResultadoVarredura`. 403 para os demais
perfis.

**`GET /completude/alertas`** — qualquer usuário autenticado. Filtros opcionais
`status`, `municipio_id`, `ano`; paginação `page` / `page_size` no mesmo
formato de `/registros` (`items`, `total`, `page`, `page_size`,
`total_pages`). Ordenação: `referencia_ano DESC, referencia_mes DESC`.
`GESTOR_MUNICIPAL` tem `municipio_id` forçado ao `municipio_alocado_id`.

**`PUT /completude/alertas/{id}`** — corpo `{"status": "INVESTIGANDO"}`.
Dependência `get_admin_only`. Status fora do conjunto permitido → 422; id
inexistente → 404. Responde o alerta atualizado.

Todos os endpoints respondem 401 sem token (middleware em `main.py`).

### `backend/app/schemas.py`

Bloco novo `# COMPLETUDE (RF15 & RF16)`:

- `AlertaCompletudeOut` — campos da tabela mais `municipio_nome` resolvido pelo
  relationship (`None` quando `municipio_id` é nulo).
- `AlertaStatusUpdate` — `status` restrito a `ABERTO`, `INVESTIGANDO`,
  `RESOLVIDO`, `FALSO_POSITIVO`.
- `PaginatedAlertas` — `items`, `total`, `page`, `page_size`, `total_pages`.
- `ResultadoVarredura` — contadores da varredura.

## Frontend

### `frontend/completude_ui.py` (novo)

`render_completude_section()`, seguindo a estrutura de `fluxo_ui.py` e usando
`COLORS` / `badge_html` de `theme.py`:

- Faixa de KPIs: total de alertas, abertos, em investigação, municípios
  afetados.
- Filtros: status (`selectbox` com opção "Todos"), município e ano.
- Tabela paginada com badge colorido por status — `ABERTO` vermelho,
  `INVESTIGANDO` âmbar, `RESOLVIDO` verde, `FALSO_POSITIVO` cinza.
- Apenas para ADMIN: botão "Executar varredura" no topo e, por linha, um
  `selectbox` de status com botão "Salvar" que chama o `PUT`. Para os demais
  perfis a tela é somente leitura.
- Erros de rede tratados via `ApiError`, como nas telas existentes.

Leituras passam por `frontend/data_cache.py` com `TTL_AGREGADO`; a varredura e
a troca de status invalidam o cache (`st.cache_data.clear()`) antes do rerun,
para a lista refletir a alteração imediatamente.

### `frontend/api_client.py`

Bloco `# --- COMPLETUDE (RF15 & RF16) ---` com `listar_alertas_completude`,
`atualizar_status_alerta` e `recalcular_completude`, no padrão de `_request` já
usado.

### Navegação (`frontend/app.py`)

Entrada nova no dicionário `PAGINAS`, posicionada depois de `fluxo` e antes das
telas de CRUD, por ser tela analítica:

```python
PAGINAS = {
    "dashboard": "📊 Dashboard Geral",
    "fluxo": "🔀 Fluxo Intermunicipal",
    "completude": "⚠️ Alertas de Completude",
    "registros": "💉 Registros de Vacinação",
    "municipios": "🏙️ Gestão de Municípios & Vacinas",
}
```

Mais o ramo correspondente no roteamento `if/elif` no fim do arquivo. A tela
aparece para todos os perfis; o que muda por perfil é o conjunto de ações
disponíveis dentro dela.

## Testes

Desenvolvimento guiado por testes: cada comportamento abaixo tem teste escrito
antes da implementação.

### `backend/tests/test_completude.py` (novo)

Serviço:

- município com queda brusca em um mês gera alerta;
- município com volume estável não gera alerta;
- mês ausente no meio do histórico vira alerta com `total_observado = 0`;
- município com menos de `minimo_meses` meses é ignorado;
- `k` maior torna a detecção menos sensível;
- reexecutar não duplica alertas e preserva status `RESOLVIDO`, atualizando
  `total_observado`.

Endpoints:

- `POST /completude/recalcular` como ADMIN retorna os contadores; como
  GESTOR_ESTADUAL e GESTOR_MUNICIPAL retorna 403;
- `GET /completude/alertas` lista com paginação e filtra por `status`;
- `GESTOR_MUNICIPAL` vê apenas alertas do município alocado;
- `PUT /completude/alertas/{id}` como ADMIN altera o status para
  `INVESTIGANDO`, `RESOLVIDO` e `FALSO_POSITIVO`;
- `PUT` como não-ADMIN retorna 403;
- `PUT` com status inválido retorna 422;
- `PUT` com id inexistente retorna 404;
- requisição sem token retorna 401.

### `frontend/tests/test_completude_ui.py` (novo)

No padrão dos testes de UI existentes, com `api_client` mockado:

- lista renderiza os alertas retornados;
- filtro por status repassa o parâmetro à chamada da API;
- botão de varredura e seletor de status não aparecem para perfis não-ADMIN;
- `ApiError` na listagem exibe mensagem de erro em vez de quebrar a tela.

## Fora de escopo

- Agendamento automático da varredura (cron, Celery, hook no ETL). O disparo é
  o endpoint `POST /completude/recalcular`, acionado pelo botão da tela. O
  serviço fica isolado justamente para que um agendador futuro apenas o chame.
- Detecção de anomalias no lado superior (volume acima do esperado).
- Notificação por e-mail dos alertas abertos.
- Registro em `log_auditoria` das mudanças de status — a auditoria hoje cobre
  `registros_vacinacao`; estender para alertas é decisão separada.
