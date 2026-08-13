import os
from typing import Any, Optional

import requests

API_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


class ApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _request(method: str, path: str, token: str, **kwargs) -> Any:
    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            **kwargs,
        )
    except requests.exceptions.ConnectionError:
        raise ApiError("Não foi possível conectar ao servidor.")
    except requests.exceptions.Timeout:
        raise ApiError("O servidor demorou para responder.")
    except requests.exceptions.RequestException:
        raise ApiError("Erro de comunicação com o servidor.")

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Erro ao processar a solicitação.")
        except ValueError:
            detail = "Erro ao processar a solicitação."
        raise ApiError(detail, status_code=response.status_code)

    if not response.content:
        return None
    return response.json()


def listar_municipios(token: str, uf: str = "", ativo: Optional[bool] = None,
                       search: str = "", page: int = 1, page_size: int = 10) -> dict:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if uf:
        params["uf"] = uf
    if ativo is not None:
        params["ativo"] = str(ativo).lower()
    if search:
        params["search"] = search
    return _request("GET", "/municipios", token, params=params)


def criar_municipio(token: str, payload: dict) -> dict:
    return _request("POST", "/municipios", token, json=payload)


def atualizar_municipio(token: str, id_ibge: str, payload: dict) -> dict:
    return _request("PUT", f"/municipios/{id_ibge}", token, json=payload)


def desativar_municipio(token: str, id_ibge: str) -> dict:
    return _request("DELETE", f"/municipios/{id_ibge}", token)
