import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

# Configuração do Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configurações do JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super_secret_key_de_desenvolvimento")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash do banco."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Gera o hash bcrypt da senha."""
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    """Gera o token JWT válido por 8 horas."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt