from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models import UsuarioAdmin
from app.schemas import LoginData, MeResponse, TokenResponse
from app.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginData, db: Session = Depends(get_db)):
    user = db.query(UsuarioAdmin).filter(UsuarioAdmin.email == login_data.email).first()

    # Critério de Aceite: Erro Genérico. Não expõe se o erro foi no email ou na senha.
    if not user or not verify_password(login_data.password, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.", 
        )

    # Gera token com payload contendo os dados necessários para o frontend
    access_token = create_access_token(
        data={
            "sub": user.email,
            "role": user.role,
            "municipio_id": user.municipio_alocado_id
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "municipio_alocado_id": user.municipio_alocado_id
    }


@router.get("/me", response_model=MeResponse)
def me(current_user: UsuarioAdmin = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "role": current_user.role,
        "municipio_alocado_id": current_user.municipio_alocado_id,
    }