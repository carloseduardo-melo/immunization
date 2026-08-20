import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, UsuarioAdmin
from app.security import get_password_hash
from app.sql_views import ensure_fluxo_view

DATABASE_URL = os.getenv("DATABASE_URL")
if os.getenv("TESTING") == "1":
    DATABASE_URL = DATABASE_URL or "sqlite:///./test.db"
elif not DATABASE_URL:
    DATABASE_URL = "sqlite:///./dev.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_fluxo_view(conn)
    ensure_default_admin_user()


def ensure_default_admin_user():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@imunizacao.local")
        password = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")

        existing_user = db.query(UsuarioAdmin).filter(UsuarioAdmin.email == email).first()
        if existing_user is not None:
            return existing_user

        default_user = UsuarioAdmin(
            email=email,
            senha_hash=get_password_hash(password),
            role="ADMIN",
        )
        db.add(default_user)
        db.commit()
        db.refresh(default_user)
        return default_user
    finally:
        db.close()
