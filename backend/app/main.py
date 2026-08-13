import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from app.database import init_db
from app.routers.auth import router as auth_router
from app.routers.municipios import router as municipios_router
from app.security import ALGORITHM, SECRET_KEY

app = FastAPI(title="Imunização API", version="1.0.0")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path == "/auth/login":
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

    if email is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Token ausente ou inválido."},
        )

    request.state.user = {"email": email}
    return await call_next(request)


app.include_router(auth_router)
app.include_router(municipios_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    if os.getenv("TESTING") != "1":
        init_db()
