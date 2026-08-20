import os
# Ensure testing env is set before importing application modules
os.environ["TESTING"] = "1"
# Default to a local sqlite test DB only if DATABASE_URL is not already set
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.sql_views import ensure_fluxo_view

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
connect_args = {}
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

if connect_args:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def initialize_test_database():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_fluxo_view(conn)
    yield
    engine.dispose()


@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()
