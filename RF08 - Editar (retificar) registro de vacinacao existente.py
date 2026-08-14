from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import date, datetime, timezone
import threading
import copy

app = FastAPI()
_lock = threading.RLock()

class Registro(BaseModel):
    id: int
    data: date
    municipio: str
    vacina: str
    teve_deslocamento: bool
    status_dado: str


class RegistroUpdate(BaseModel):
    data: Optional[date] = None
    municipio: Optional[str] = None
    vacina: Optional[str] = None

    @validator("municipio", "vacina")
    def not_empty_str(cls, v):
        if v is not None and not v.strip():
            raise ValueError("não pode ser string vazia")
        return v


registros: Dict[int, Dict[str, Any]] = {
    1: {
        "id": 1,
        "data": "2026-08-10",
        "municipio": "Pedra Branca",
        "vacina": "COVID-19",
        "teve_deslocamento": False,
        "status_dado": "OK",
    }
}

log_auditoria = []


def recalcular_dados(registro: Dict[str, Any]) -> None:
    """
    Recalcula os campos derivados após a edição.
    Operamos com strings ISO na chave 'data'.
    """

    registro["teve_deslocamento"] = registro.get("municipio") != "Pedra Branca"

    if registro.get("data") and registro.get("municipio") and registro.get("vacina"):
        registro["status_dado"] = "OK"
    else:
        registro["status_dado"] = "INCOMPLETO"


@app.patch("/registros/{id}", response_model=Registro)
def editar_registro(id: int, dados: RegistroUpdate):
    """
    Atualização parcial do registro (PATCH).
    Valida a data via Pydantic; armazena a data em ISO (YYYY-MM-DD).
    """

    with _lock:
        if id not in registros:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado")

        registro = registros[id]

        valores_antigos = copy.deepcopy(registro)

        if dados.data is not None:
            registro["data"] = dados.data.isoformat()

        if dados.municipio is not None:
            registro["municipio"] = dados.municipio

        if dados.vacina is not None:
            registro["vacina"] = dados.vacina

        recalcular_dados(registro)

        valores_novos = copy.deepcopy(registro)

        changed_fields = [
            key for key in valores_novos.keys()
            if valores_antigos.get(key) != valores_novos.get(key)
        ]
 
        log_auditoria.append({
            "registro_id": id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "valor_antigo": valores_antigos,
            "valor_novo": valores_novos,
            "changed_fields": changed_fields,
        })

        
        response_obj = {
            "id": registro["id"],
            "data": date.fromisoformat(registro["data"]) if registro.get("data") else None,
            "municipio": registro.get("municipio"),
            "vacina": registro.get("vacina"),
            "teve_deslocamento": registro.get("teve_deslocamento"),
            "status_dado": registro.get("status_dado"),
        }

        return response_obj