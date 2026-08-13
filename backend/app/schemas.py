from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class LoginData(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    municipio_alocado_id: Optional[str] = None


class MunicipioBase(BaseModel):
    nome: str
    uf: str
    regiao_saude: Optional[str] = None
    polo: bool = False

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("O nome do município é obrigatório.")
        return v.strip()

    @field_validator("uf")
    @classmethod
    def uf_valida(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("UF deve conter exatamente 2 letras.")
        return v


class MunicipioCreate(MunicipioBase):
    id_ibge: str

    @field_validator("id_ibge")
    @classmethod
    def id_ibge_valido(cls, v: str) -> str:
        if not v or not v.isdigit() or len(v) != 7:
            raise ValueError("id_ibge deve conter exatamente 7 dígitos numéricos.")
        return v


class MunicipioUpdate(MunicipioBase):
    pass


class MunicipioOut(MunicipioBase):
    id_ibge: str
    ativo: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedMunicipios(BaseModel):
    items: list[MunicipioOut]
    total: int
    page: int
    page_size: int
    total_pages: int
