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


def obter_me(token: str) -> dict:
    return _request("GET", "/auth/me", token)


# --- MUNICÍPIOS ---

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


# --- VACINAS (RF04 & RF05) ---

def listar_vacinas(token: str, alta_complexidade: Optional[bool] = None, ativo: Optional[bool] = None,
                   search: str = "", page: int = 1, page_size: int = 10) -> dict:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if alta_complexidade is not None:
        params["alta_complexidade"] = str(alta_complexidade).lower()
    if ativo is not None:
        params["ativo"] = str(ativo).lower()
    if search:
        params["search"] = search
    return _request("GET", "/vacinas", token, params=params)


def criar_vacina(token: str, payload: dict) -> dict:
    return _request("POST", "/vacinas", token, json=payload)


def atualizar_vacina(token: str, vacina_id: Any, payload: dict) -> dict:
    return _request("PUT", f"/vacinas/{vacina_id}", token, json=payload)


def desativar_vacina(token: str, vacina_id: Any) -> dict:
    return _request("DELETE", f"/vacinas/{vacina_id}", token)


# --- REGISTROS DE VACINAÇÃO (RF06, RNF01, RNF08) ---

def listar_registros(token: str, search: str = "", page: int = 1, page_size: int = 10, **kwargs) -> dict:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if search:
        params["search"] = search
    params.update({k: v for k, v in kwargs.items() if v})
    return _request("GET", "/registros", token, params=params)


def criar_registro(token: str, payload: dict) -> dict:
    return _request("POST", "/registros", token, json=payload)


def atualizar_registro(token: str, registro_id: str, payload: dict) -> dict:
    return _request("PUT", f"/registros/{registro_id}", token, json=payload)


def desativar_registro(token: str, registro_id: str) -> dict:
    return _request("DELETE", f"/registros/{registro_id}", token)


# --- DASHBOARD PRINCIPAL (RF23) ---

def obter_resumo_dashboard(token: str, municipio_id: str = None, vacina_id: int = None, ano: int = None) -> dict:
    params: dict[str, Any] = {}
    if municipio_id:
        params["municipio_id"] = municipio_id
    if vacina_id:
        params["vacina_id"] = vacina_id
    if ano:
        params["ano"] = ano
    return _request("GET", "/dashboard/resumo", token, params=params)