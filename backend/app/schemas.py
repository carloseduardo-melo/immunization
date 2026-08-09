from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginData(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    municipio_alocado_id: Optional[str] = None