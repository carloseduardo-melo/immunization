from typing import Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UsuarioAdmin
from app.security import ALGORITHM, SECRET_KEY

# Esquema OAuth2 que diz ao FastAPI onde buscar o token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Middleware: Exige Token JWT válido. Retorna 401 se ausente ou expirado."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ausente ou inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:  # pragma: no cover - coberto via JWTError abaixo
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(UsuarioAdmin).filter(UsuarioAdmin.email == email).first()
    if user is None:
        raise credentials_exception
    return user


def require_role(roles: list[str]):
    """Middleware RBAC: Verifica se o usuário tem o perfil adequado."""

    def role_checker(current_user: UsuarioAdmin = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operação não permitida para o seu perfil de acesso.",
            )
        return current_user

    return role_checker


def validate_municipio_scope(current_user: UsuarioAdmin, municipio_id: str | None = None):
    """Restringe gestores municipais ao município vinculado ao perfil."""
    if current_user.role in {"ADMIN", "GESTOR_ESTADUAL"}:
        return current_user

    if current_user.role != "GESTOR_MUNICIPAL":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil sem permissão para acessar este município.",
        )

    if current_user.municipio_alocado_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gestor municipal sem município vinculado.",
        )

    if municipio_id is not None and str(municipio_id) != str(current_user.municipio_alocado_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a este município.",
        )

    return current_user


def require_municipio_access(municipio_id: str | None = None):
    """Dependency para restringir acesso por município."""

    def municipio_checker(current_user: UsuarioAdmin = Depends(get_current_user)):
        return validate_municipio_scope(current_user, municipio_id)

    return municipio_checker


# Dependências prontas para injetar nas rotas de CRUD
get_admin_user = require_role(["ADMIN"])
get_estadual_admin_user = require_role(["ADMIN", "GESTOR_ESTADUAL"])
get_admin_and_estadual = require_role(["ADMIN", "GESTOR_ESTADUAL"])
get_admin_only = require_role(["ADMIN"])