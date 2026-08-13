from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UsuarioAdmin
from app.security import SECRET_KEY, ALGORITHM

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
        if email is None:
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
                detail="Operação não permitida para o seu perfil de acesso."
            )
        return current_user
    return role_checker

# Dependências prontas para injetar nas rotas de CRUD
get_admin_user = require_role(["ADMIN"])
get_estadual_admin_user = require_role(["ADMIN", "GESTOR_ESTADUAL"])