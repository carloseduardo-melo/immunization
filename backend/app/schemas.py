from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class LoginData(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_valido(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("O e-mail é obrigatório.")
        return value.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    municipio_alocado_id: Optional[str] = None


class MeResponse(BaseModel):
    email: str
    role: str
    municipio_alocado_id: Optional[str] = None


# ==========================================
# MUNICÍPIOS
# ==========================================

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


# ==========================================
# VACINAS (RF04 & RF05)
# ==========================================

class VacinaBase(BaseModel):
    nome: str
    alta_complexidade: bool = False

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("O nome da vacina é obrigatório.")
        return v.strip()


class VacinaCreate(VacinaBase):
    pass


class VacinaUpdate(VacinaBase):
    pass


class VacinaOut(VacinaBase):
    id: int
    ativo: bool

    class Config:
        from_attributes = True


class PaginatedVacinas(BaseModel):
    items: list[VacinaOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==========================================
# REGISTROS DE VACINAÇÃO (RF06, RNF01, RNF08)
# ==========================================

class RegistroVacinacaoOut(BaseModel):
    id: UUID
    data_vacinacao: date
    idade: Optional[int] = None
    vacina_id: Optional[int] = None
    vacina_nome: Optional[str] = None
    municipio_residencia_id: Optional[str] = None
    municipio_residencia_nome: Optional[str] = None
    municipio_vacina_id: str
    municipio_vacina_nome: Optional[str] = None
    teve_deslocamento: Optional[bool] = None
    quantidade: int
    status_dado: str

    class Config:
        from_attributes = True


class RegistroVacinacaoCreate(BaseModel):
    data_vacinacao: date
    municipio_vacina_id: str
    municipio_residencia_id: Optional[str] = None
    vacina_id: Optional[int] = None
    idade: Optional[int] = None
    quantidade: int = 1

    @field_validator("municipio_vacina_id")
    @classmethod
    def municipio_vacina_valido(cls, v: str) -> str:
        v_clean = (v or "").strip()
        if not v_clean or not v_clean.isdigit() or len(v_clean) != 7:
            raise ValueError("O código IBGE do município de aplicação é obrigatório e deve conter exatamente 7 dígitos.")
        return v_clean

    @field_validator("municipio_residencia_id")
    @classmethod
    def municipio_residencia_valido(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = v.strip()
        if not v_clean:
            return None
        if not v_clean.isdigit() or len(v_clean) != 7:
            raise ValueError("O código IBGE do município de residência deve conter exatamente 7 dígitos.")
        return v_clean

    @field_validator("quantidade")
    @classmethod
    def quantidade_positiva(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("A quantidade deve ser um valor positivo maior que zero.")
        return v


class PaginatedRegistros(BaseModel):
    items: list[RegistroVacinacaoOut]
    total: int
    page: int
    page_size: int
    total_pages: int