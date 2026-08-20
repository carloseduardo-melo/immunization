"""Camada de leitura com cache entre a UI e a API.

`api_client.py` continua sendo o cliente HTTP puro (sem dependência de
Streamlit, testável isoladamente). Aqui ficam apenas os envoltórios com
`st.cache_data`, para que um rerun do Streamlit — que reexecuta o script
inteiro a cada clique — não refaça as mesmas chamadas de rede.

O ganho maior é em `listar_municipios_resumido`: a lista completa de
municípios exige ~39 requisições paginadas à API, e sem cache isso era
repetido a cada interação do usuário.

TTLs: municípios e vacinas são dados de cadastro, alterados esporadicamente
por um gestor, então 10 minutos de validade é um limite de defasagem
confortável. Os agregados de fluxo derivam da view materializada, que é
atualizada a cada escrita em /registros; 5 minutos mantém o painel coerente
com edições recentes sem repetir a agregação a cada rerun.
"""

import streamlit as st

from api_client import (
    listar_alertas_completude,
    listar_todos_municipios,
    listar_vacinas,
    obter_fluxo_intermunicipal,
    obter_ranking_fluxo,
    obter_resumo_dashboard,
)

TTL_CADASTRO = 600
TTL_AGREGADO = 300


@st.cache_data(ttl=TTL_CADASTRO, show_spinner=False)
def listar_municipios_resumido(token: str) -> list[tuple[str, str]]:
    """Devolve apenas (id_ibge, nome) de cada município.

    A API responde o objeto completo (uf, região, timestamps...), mas as telas
    só usam código e nome para montar os seletores. Guardar somente esses dois
    campos reduz bastante o que fica retido em memória no servidor.
    """
    municipios = listar_todos_municipios(token)
    return [(m["id_ibge"], m["nome"]) for m in municipios]


@st.cache_data(ttl=TTL_CADASTRO, show_spinner=False)
def listar_vacinas_resumido(token: str) -> list[tuple[int, str]]:
    """Devolve apenas (id, nome) de cada vacina, pelo mesmo motivo acima."""
    itens = listar_vacinas(token, page_size=100).get("items", [])
    return [(v["id"], v["nome"]) for v in itens]


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def fluxo_intermunicipal(
    token: str,
    vacina_id=None,
    data_inicio=None,
    data_fim=None,
    municipio_id=None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    return obter_fluxo_intermunicipal(
        token,
        vacina_id=vacina_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        municipio_id=municipio_id,
        page=page,
        page_size=page_size,
    )


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def ranking_fluxo(
    token: str, vacina_id=None, data_inicio=None, data_fim=None, limit: int = 10
) -> dict:
    return obter_ranking_fluxo(
        token,
        vacina_id=vacina_id,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limit=limit,
    )


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def resumo_dashboard(token: str, municipio_id=None, vacina_id=None, ano=None) -> dict:
    return obter_resumo_dashboard(
        token, municipio_id=municipio_id, vacina_id=vacina_id, ano=ano
    )


@st.cache_data(ttl=TTL_AGREGADO, show_spinner=False)
def alertas_completude(
    token: str,
    status=None,
    municipio_id=None,
    ano=None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """Listagem de alertas com o mesmo TTL dos demais agregados: a varredura e a
    troca de status limpam o cache explicitamente, então 5 minutos aqui só evita
    repetir a consulta a cada rerun do Streamlit."""
    return listar_alertas_completude(
        token,
        status=status,
        municipio_id=municipio_id,
        ano=ano,
        page=page,
        page_size=page_size,
    )
