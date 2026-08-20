import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.municipios import router as municipios_router
from app.routers.registros import router as registros_router
from app.routers.vacinas import router as vacinas_router
from app.routers.dashboard import router as dashboard_router
from app.routers.fluxo import router as fluxo_router
from app.routers.completude import router as completude_router
from app.security import ALGORITHM, SECRET_KEY

API_DESCRIPTION = """
API do sistema de acompanhamento de imunização municipal.

Permite autenticar administradores, cadastrar municípios e vacinas, e
registrar, consultar, retificar e excluir logicamente registros
individuais de vacinação, além de expor indicadores agregados para o
dashboard.

### Autenticação

Todos os endpoints, exceto `POST /auth/login` e `GET /health`, exigem um
token JWT enviado no cabeçalho `Authorization: Bearer <token>`. Obtenha o
token em `/auth/login` e use o botão **Authorize** acima para aplicá-lo
às chamadas feitas a partir desta página.
"""

OPENAPI_TAGS = [
    {
        "name": "Autenticação",
        "description": "Login e identificação do usuário autenticado.",
    },
    {
        "name": "Municípios",
        "description": "Cadastro, edição e consulta de municípios (perfil ADMIN/GESTOR_ESTADUAL para escrita).",
    },
    {
        "name": "Vacinas",
        "description": "Cadastro, edição e consulta de vacinas (perfil ADMIN/GESTOR_ESTADUAL para escrita).",
    },
    {
        "name": "Registros",
        "description": "Cadastro, retificação, exclusão lógica e consulta de registros individuais de vacinação.",
    },
    {
        "name": "Dashboard",
        "description": "Indicadores agregados (KPIs e série temporal) a partir dos registros ativos.",
    },
    {
        "name": "Fluxo Intermunicipal",
        "description": "Mobilidade vacinal origem x destino e ranking de municípios-polo/evasão, a partir da view mv_fluxo_intermunicipal.",
    },
    {
        "name": "Completude",
        "description": (
            "Alertas de completude de dados: varredura automática de meses/municípios "
            "fora do padrão e gestão do status dos alertas (perfil ADMIN para escrita)."
        ),
    },
]

app = FastAPI(
    title="Imunização API",
    version="1.0.0",
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
)

# Caminhos que não exigem token: login, health check e a própria
# documentação (o Swagger UI precisa carregar antes que o usuário tenha
# um token para clicar em "Authorize").
_PUBLIC_PATHS = {"/auth/login", "/health", "/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Token ausente ou inválido."},
        )

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise JWTError
    except JWTError:
        return JSONResponse(
            status_code=401,
            content={"detail": "Token ausente ou inválido."},
        )

    if email is None:  # pragma: no cover - já garantido no bloco try acima
        return JSONResponse(
            status_code=401,
            content={"detail": "Token ausente ou inválido."},
        )

    request.state.user = {"email": email}
    return await call_next(request)


app.include_router(auth_router)
app.include_router(municipios_router)
app.include_router(vacinas_router)
app.include_router(registros_router)
app.include_router(dashboard_router)
app.include_router(fluxo_router)
app.include_router(completude_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():  # pragma: no cover - desligado sob pytest (TESTING=1)
    if os.getenv("TESTING") != "1":
        init_db()
