import os

from fastapi import FastAPI
from app.database import init_db
from app.routers.auth import router as auth_router

app = FastAPI(title="Imunização API", version="1.0.0")

app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.on_event("startup")
def on_startup():
    if os.getenv("TESTING") != "1":
        init_db()
