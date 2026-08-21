# RF17 - Painel de sazonalidade e RF18 - Painel de imunobiologicos de alta complexidade

Data: 2026-08-20
Branch: feature/22-23-monitor-completude

## Objetivo

Dois paineis analiticos novos, cada um com endpoint proprio no backend e tela
propria no frontend, alcancaveis pela navegacao lateral:

- **RF17 - Sazonalidade**: volume de vacinacao por mes do ano, para apoiar o
  planejamento de campanhas.
- **RF18 - Alta complexidade**: para cada vacina marcada como
  `alta_complexidade`, a taxa de deslocamento e os municipios que funcionam como
  centro de referencia regional.

## Criterios de aceite

RF17:
1. Grafico de barras com o volume mensal de vacinacao.
2. Filtro por vacina e por municipio.

RF18:
1. Lista as vacinas com `alta_complexidade = true` e a taxa de deslocamento de
   cada uma.
2. Para cada vacina, mostra o(s) municipio(s) com maior volume de aplicacao
   (centro de referencia).

## Decisoes de projeto

**Sazonalidade e mes do ano, nao serie cronologica.** As 12 barras consolidam
todos os anos do recorte (Jan..Dez). E o que caracteriza sazonalidade e apoia a
decisao "em qual mes concentrar a campanha". A serie cronologica ano-a-mes ja
existe no Dashboard Geral (`/dashboard/resumo`), e duplica-la aqui nao
acrescentaria informacao.

**Indice de sazonalidade.** Cada mes traz `total_doses` e
`indice_sazonalidade = total_do_mes / media_mensal` (1,00 = mes medio). O total
absoluto sozinho nao diz se um mes e alto ou baixo sem o leitor fazer a conta de
cabeca; o indice traduz o grafico em decisao.

**Estrutura: um router e um modulo de UI por RF.** Sazonalidade (temporal) e
alta complexidade (por imunobiologico) sao dominios distintos e nao compartilham
consulta nem filtro. Arquivos pequenos e focados tambem sao o que torna
alcancavel a cobertura de 100% exigida pelos dois `pytest.ini`.

**Sem restricao por municipio.** Os dois endpoints usam `get_current_user`
(leitura autenticada), sem `validate_municipio_scope`. Sao paineis analiticos
estaduais, como `/dashboard` e `/fluxo`. O RF18 em particular perde o sentido se
um gestor municipal so enxergar o proprio municipio: o requisito e justamente
comparar municipios para identificar o centro de referencia regional.
`/completude` restringe porque trata de pendencia operacional do municipio, o
que nao e o caso aqui.

**Agregacao direta em `registros_vacinacao`, sem view materializada nova.** O
RF17 agrupa por mes com `func.extract`, a mesma tecnica ja usada em
`dashboard.py` e que funciona tanto em PostgreSQL (producao) quanto em SQLite
(dev.db/test.db). O RF18 filtra por um subconjunto pequeno de vacinas e conta
com os indices `idx_registro_vacina` e `idx_registro_local` ja existentes. A
`mv_fluxo_intermunicipal` nao serve ao RF18: ela contem apenas registros com
deslocamento real, e a taxa de deslocamento precisa do denominador completo.

## RF17 - Backend

`GET /sazonalidade`, router `backend/app/routers/sazonalidade.py`, tag
"Sazonalidade".

Parametros (todos opcionais):

| Parametro | Tipo | Efeito |
|---|---|---|
| `vacina_id` | int | `RegistroVacinacao.vacina_id == vacina_id` |
| `municipio_id` | str | `RegistroVacinacao.municipio_vacina_id == municipio_id` (municipio de aplicacao, igual ao Dashboard) |
| `ano_inicio` | int | `extract('year', data_vacinacao) >= ano_inicio` |
| `ano_fim` | int | `extract('year', data_vacinacao) <= ano_fim` |

Regras:

- Considera apenas `ativo == true`. Todos os `status_dado` entram: o mes vem de
  `data_vacinacao`, que e `NOT NULL` e nao e afetada pelas inconsistencias de
  idade ou de deslocamento. Sazonalidade mede volume de coleta, nao validade.
- A resposta traz **sempre os 12 meses**, em ordem de 1 a 12. Meses sem registro
  voltam com `total_doses = 0` e `indice_sazonalidade = 0.0`, para o grafico nao
  pular meses.
- `media_mensal = total_periodo / 12`. O divisor e fixo em 12 (e nao "meses com
  dado") para que o indice de um mes zerado seja 0,0 e a soma dos indices seja
  sempre 12 - caso contrario o indice mudaria de significado conforme quantos
  meses tem dado.
- Quando `media_mensal == 0` (recorte sem nenhum registro), todos os
  `indice_sazonalidade` sao `0.0` - a divisao nao chega a ser feita.
- `mes_pico` e o mes de maior `total_doses`; `mes_vale`, o de menor. Empate e
  resolvido pelo menor numero de mes (o primeiro no ano), para a resposta ser
  deterministica.
- `amplitude = total_do_mes_pico / total_do_mes_vale`, arredondado a 2 casas.
  Se o mes de vale for 0, `amplitude = 0.0` (nao ha divisao por zero).
- Base vazia no recorte: 12 meses zerados, `mes_pico` e `mes_vale` iguais a
  `None`, `amplitude = 0.0`, `total_periodo = 0`. A tela mostra um aviso.
- Percentuais e indices sao arredondados a 2 casas, como ja se faz em
  `taxa_mobilidade`.

Schemas em `backend/app/schemas.py`:

```python
class SazonalidadeMes(BaseModel):
    mes: int                     # 1..12
    nome_mes: str                # "Jan".."Dez"
    total_doses: int
    indice_sazonalidade: float   # total do mes / media mensal

class SazonalidadeKPIs(BaseModel):
    total_periodo: int
    media_mensal: float
    mes_pico: Optional[int]
    mes_pico_nome: Optional[str]
    mes_vale: Optional[int]
    mes_vale_nome: Optional[str]
    amplitude: float

class SazonalidadeResponse(BaseModel):
    kpis: SazonalidadeKPIs
    meses: list[SazonalidadeMes]
```

## RF18 - Backend

`GET /alta-complexidade`, router `backend/app/routers/alta_complexidade.py`,
tag "Alta Complexidade".

Parametro opcional `top_municipios` (padrao 3, minimo 1, teto 10) - quantos
municipios de maior volume retornar por vacina.

Regras:

- Universo: vacinas com `alta_complexidade == true` **e** `ativo == true`.
- Ordenacao das vacinas por `total_doses` desc, depois por `nome` (desempate
  estavel).
- Por vacina:
  - `total_doses`: soma de `quantidade` dos registros ativos com
    `status_dado != 'DADO_INCONSISTENTE'`.
  - `total_deslocamentos`: dentro dessa mesma base, os com
    `teve_deslocamento == true`.
  - `total_indeterminado`: dentro dessa mesma base, os com
    `teve_deslocamento IS NULL` (origem desconhecida - ETL nao tem municipio
    de residencia e marca `DESLOCAMENTO_INDETERMINADO`). O criterio e
    `teve_deslocamento IS NULL`, nao `status_dado`, porque e o que garante por
    construcao que este numero seja subconjunto de `total_doses`.
  - `taxa_deslocamento`: `total_deslocamentos / (total_doses -
    total_indeterminado) * 100`, 2 casas; `0.0` quando o denominador for zero.
    Essas doses entram em `total_doses` (volume aplicado e volume aplicado,
    e o ranking de municipios depende do total cheio) mas nunca podem entrar
    no numerador de deslocamento - deixa-las no denominador da taxa diluiria o
    resultado de forma desigual entre vacinas e municipios, conforme a fatia
    de origem desconhecida de cada um. A taxa passa a responder "das doses
    cuja origem conhecemos, quantas foram deslocadas".
  - Exclui `DADO_INCONSISTENTE` do numerador e do denominador - a estatistica
    mais defensavel para este painel. Difere do `taxa_mobilidade` de
    `/dashboard/resumo`, que usa base mista (denominador com inconsistentes,
    numerador sem); por isso a taxa aqui pode divergir da taxa de mobilidade
    do Dashboard para a mesma vacina - e decisao de projeto, nao bug.
- Top N municipios por vacina: agregacao por `municipio_vacina_id` na mesma base,
  ordenada por doses desc, com `percentual` = doses do municipio / total da
  vacina * 100 (2 casas). Empate resolvido pelo menor `municipio_vacina_id`,
  para a resposta ser deterministica - o mesmo problema e a mesma solucao do
  `mes_pico`/`mes_vale` do RF17. O primeiro da lista e o centro de referencia
  (`centro_referencia_*` no topo do item, para a tela nao precisar olhar dentro
  da lista).
- Vacina de alta complexidade sem nenhum registro aparece com zeros e
  `municipios = []`. Omiti-la esconderia do gestor exatamente o caso que ele
  precisa investigar.
- Duas consultas agregadas no banco (uma por vacina, uma por vacina x
  municipio). O corte do top N acontece em Python sobre o agregado ja reduzido -
  sao poucas vacinas de alta complexidade, e a alternativa (window function) nao
  roda igual em SQLite.

Schemas:

```python
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
    total_indeterminado: int
    taxa_deslocamento: float
    centro_referencia_id: Optional[str]
    centro_referencia_nome: Optional[str]
    municipios: list[MunicipioAplicacaoItem]

class AltaComplexidadeResponse(BaseModel):
    items: list[VacinaAltaComplexidadeItem]
    total_vacinas: int
```

## Frontend

`api_client.py` (cliente HTTP puro, sem Streamlit):

- `obter_sazonalidade(token, vacina_id=None, municipio_id=None, ano_inicio=None, ano_fim=None)`
- `obter_alta_complexidade(token, top_municipios=3)`

`data_cache.py`: envoltorios `sazonalidade()` e `alta_complexidade()` com
`@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)`, como os demais agregados.

### Tela RF17 - `frontend/sazonalidade_ui.py`

`render_sazonalidade_section()`, item de menu `📅 Sazonalidade`.

- Guarda de autenticacao (`st.warning` sem token), igual as demais telas.
- Titulo (`page-title`) e subtitulo (`page-subtitle`) no padrao do design system.
- Filtros dentro de `st.container(border=True)`, em 4 colunas: Imunobiologico,
  Municipio de Aplicacao, Ano inicial, Ano final. As listas vem de
  `listar_vacinas_resumido` / `listar_municipios_resumido`; falha delas cai em
  lista vazia e a tela continua util (mesmo tratamento de `completude_ui`).
- Quatro `st.metric` em `st.container(border=True)`: mes de pico, mes de vale,
  amplitude, total do periodo.
- `st.bar_chart` com os 12 meses (componente nativo, sem dependencia nova).
- Tabela com mes, doses e indice, marcando o pico com um triangulo para cima e o
  vale com um triangulo para baixo.
- Recorte sem dado: `st.info` explicando que nao ha registros no periodo, sem
  grafico.

### Tela RF18 - `frontend/alta_complexidade_ui.py`

`render_alta_complexidade_section()`, item de menu `🧬 Alta Complexidade`.

- Guarda de autenticacao, titulo e subtitulo no mesmo padrao.
- Seletor de quantos municipios exibir por vacina (3 / 5 / 10) - envia
  `top_municipios`.
- KPIs: numero de vacinas de alta complexidade e taxa geral de deslocamento
  delas - soma dos deslocamentos dividida pela soma das doses de todas as
  vacinas listadas (ponderada pelo volume, nao media das taxas: uma vacina com
  20 doses nao pode pesar igual a uma com 20 mil). Calculada na tela a partir
  dos totais ja retornados, sem campo novo no endpoint.
- Uma linha por vacina, com nome, total de doses, taxa de deslocamento em
  `badge_html` e o centro de referencia em destaque. Tom do badge: `danger`
  acima de 50%, `warning` de 25% a 50%, `neutral` abaixo de 25%.
- Cada vacina e um `st.expander` com o ranking dos top N municipios (posicao,
  nome, doses, % da vacina). Vacina sem registro exibe um aviso curto no lugar
  da lista.
- Nenhuma vacina de alta complexidade cadastrada: `st.info` orientando a marcar
  a flag em Gestao de Municipios & Vacinas.

### Navegacao - `frontend/app.py`

Dois itens novos no dicionario `PAGINAS`, posicionados depois de `fluxo` e antes
de `completude` (os paineis analiticos ficam agrupados no topo do menu):

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

E os dois ramos correspondentes no roteamento central (`if
st.session_state["pagina_ativa"] == ...`).

### Registro no backend - `backend/app/main.py`

Os dois routers entram em `app.include_router(...)` e ganham entrada em
`OPENAPI_TAGS`, descrevendo o que cada painel expoe.

## Testes

Os dois `pytest.ini` exigem `--cov-fail-under=100`, entao cada ramo novo precisa
de teste, inclusive os `except ApiError` das telas.

Backend - `backend/tests/test_sazonalidade.py`:
- 401 sem token.
- Distribuicao por mes correta e sempre com 12 entradas.
- Filtro por vacina, por municipio e por faixa de anos (`ano_inicio`/`ano_fim`).
- Indice de sazonalidade, mes de pico, mes de vale e amplitude.
- Base vazia (12 zeros, pico/vale `None`, amplitude 0.0).
- Mes de vale zerado nao divide por zero.

Backend - `backend/tests/test_alta_complexidade.py`:
- 401 sem token.
- So vacinas com `alta_complexidade = true` e `ativo = true` aparecem.
- Taxa de deslocamento ignorando `DADO_INCONSISTENTE`.
- Ordenacao das vacinas por doses desc.
- Top N de municipios, corte pelo `top_municipios` e clamp no minimo e no teto.
- Centro de referencia = municipio de maior volume.
- Vacina de alta complexidade sem registro (zeros e lista vazia).

Frontend - `frontend/tests/test_sazonalidade_ui.py` e
`test_alta_complexidade_ui.py`, com `AppTest.from_file("app.py")` e
`pagina_ativa` na sessao, no mesmo formato de `test_completude_ui.py`:
- Render feliz (KPIs, grafico, tabela / linhas e expanders).
- `ApiError` na chamada principal -> `st.error`.
- `ApiError` nas listas de apoio -> tela continua renderizando.
- Recorte vazio / nenhuma vacina de alta complexidade -> `st.info`.
- Sem token -> `st.warning`.
- Troca de filtro e do `top_municipios`.

Frontend - complementos:
- `test_api_client.py`: montagem de parametros das duas funcoes novas, com e sem
  filtros.
- `test_data_cache.py`: os dois envoltorios delegam ao `api_client`.
- Navegacao: clique nos dois itens novos do menu leva a pagina certa.

## Fora de escopo

- Exportacao dos paineis (CSV/PDF).
- Previsao ou projecao de demanda a partir da sazonalidade.
- Alterar `/dashboard/resumo`, `/fluxo` ou `/completude`.
- Nova migracao Alembic: nenhum dos dois paineis precisa de tabela ou coluna
  nova.
