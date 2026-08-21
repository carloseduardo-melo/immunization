from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoginData(BaseModel):
    email: str = Field(..., examples=["admin@saude.gov.br"])
    password: str = Field(..., examples=["senha123"])

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
    nome: str = Field(..., examples=["Fortaleza"])
    uf: str = Field(..., examples=["CE"])
    regiao_saude: Optional[str] = Field(None, examples=["Região de Fortaleza"])
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
    id_ibge: str = Field(..., examples=["2304400"])

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
    nome: str = Field(..., examples=["COVID-19"])
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
    data_vacinacao: date = Field(..., examples=["2024-05-20"])
    municipio_vacina_id: str = Field(..., examples=["2304400"])
    municipio_residencia_id: Optional[str] = Field(None, examples=["2303709"])
    vacina_id: Optional[int] = Field(None, examples=[1])
    idade: Optional[int] = Field(None, examples=[30])
    quantidade: int = Field(1, examples=[1])

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


class RegistroVacinacaoUpdate(RegistroVacinacaoCreate):
    pass


class PaginatedRegistros(BaseModel):
    items: list[RegistroVacinacaoOut]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==========================================
# DASHBOARD (RF23)
# ==========================================

class DashboardKPIs(BaseModel):
    total_doses: int
    total_deslocamentos: int
    taxa_mobilidade: float
    total_inconsistentes: int


class DashboardSeriePonto(BaseModel):
    mes: str
    deslocou: Optional[bool] = None
    total: int


class DashboardResumo(BaseModel):
    kpis: DashboardKPIs
    grafico: list[DashboardSeriePonto]


# ==========================================
# FLUXO INTERMUNICIPAL (RF13 & RF14)
# ==========================================

class FluxoIntermunicipalItem(BaseModel):
    municipio_origem_id: str
    municipio_origem_nome: str
    municipio_destino_id: str
    municipio_destino_nome: str
    total_doses: int


class FluxoIntermunicipalResponse(BaseModel):
    items: list[FluxoIntermunicipalItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    total_doses: int


class RankingMunicipioItem(BaseModel):
    municipio_id: str
    municipio_nome: str
    total_recebido: int
    total_perdido: int
    saldo_liquido: int


class FluxoRankingResponse(BaseModel):
    top_polo: list[RankingMunicipioItem]
    top_evasao: list[RankingMunicipioItem]


# ==========================================
# COMPLETUDE (RF15 & RF16)
# ==========================================


class AlertaCompletudeOut(BaseModel):
    id: UUID
    referencia_ano: int
    referencia_mes: int
    municipio_id: Optional[str] = None
    municipio_nome: Optional[str] = None
    total_observado: int
    status: str
    criado_em: datetime


class AlertaStatusUpdate(BaseModel):
    status: Literal["ABERTO", "INVESTIGANDO", "RESOLVIDO", "FALSO_POSITIVO"]


class PaginatedAlertas(BaseModel):
    items: list[AlertaCompletudeOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    totais_por_status: dict[str, int]
    municipios_afetados: int


class ResultadoVarredura(BaseModel):
    alertas_criados: int
    alertas_atualizados: int
    municipios_analisados: int
    meses_analisados: int


# ==========================================
# SAZONALIDADE (RF17)
# ==========================================


class SazonalidadeMes(BaseModel):
    mes: int
    nome_mes: str
    total_doses: int
    indice_sazonalidade: float


class SazonalidadeKPIs(BaseModel):
    total_periodo: int
    media_mensal: float
    mes_pico: Optional[int] = None
    mes_pico_nome: Optional[str] = None
    mes_vale: Optional[int] = None
    mes_vale_nome: Optional[str] = None
    amplitude: float


class SazonalidadeResponse(BaseModel):
    kpis: SazonalidadeKPIs
    meses: list[SazonalidadeMes]


# ==========================================
# ALTA COMPLEXIDADE (RF18)
# ==========================================


class MunicipioAplicacaoItem(BaseModel):
    municipio_id: str
    municipio_nome: str
    total_doses: int
    percentual: float


class VacinaAltaComplexidadeItem(BaseModel):
    vacina_id: int
    vacina_nome: str
    total_doses: int
    total_deslocamentos: int
    taxa_deslocamento: float
    centro_referencia_id: Optional[str] = None
    centro_referencia_nome: Optional[str] = None
    municipios: list[MunicipioAplicacaoItem]


class AltaComplexidadeResponse(BaseModel):
    items: list[VacinaAltaComplexidadeItem]
    total_vacinas: int