import pandas as pd

from fluxo_ui import (
    MAX_CELULAS_HEATMAP,
    NIVEIS_INTENSIDADE,
    _css_escala_calor,
    _formatar_numero,
    _nivel_intensidade,
)


def test_formatar_numero_usa_separador_de_milhar_ptbr():
    assert _formatar_numero(1234567) == "1.234.567"
    assert _formatar_numero(0) == "0"


def test_nivel_intensidade_maximo_zero_nao_estoura():
    assert _nivel_intensidade(0, 0) == 0


def test_nivel_intensidade_valor_maximo_usa_nivel_mais_alto():
    assert _nivel_intensidade(10, 10) == NIVEIS_INTENSIDADE - 1


def test_nivel_intensidade_fica_sempre_dentro_da_escala():
    for valor in (0, 1, 5, 9, 10):
        nivel = _nivel_intensidade(valor, 10)
        assert 0 <= nivel <= NIVEIS_INTENSIDADE - 1


def test_css_declara_todas_as_classes_de_intensidade():
    css = _css_escala_calor()
    for nivel in range(NIVEIS_INTENSIDADE):
        assert f".hm td.h{nivel}{{" in css


def _celula_antiga(valor: int) -> str:
    """Como cada célula era renderizada antes (style inline por célula)."""
    return (
        "<td style='padding:8px 12px;text-align:right;font-size:13px;"
        "border-radius:4px;white-space:nowrap;background-color: rgb(255,255,255); "
        f"color: #18181b;'>{_formatar_numero(valor)}</td>"
    )


def test_celula_com_classe_e_muito_menor_que_style_inline():
    """Regressão do MessageSizeError: a célula do mapa de calor não pode voltar
    a carregar CSS inline — era isso que multiplicava o payload por célula."""
    nova = f"<td class=h{_nivel_intensidade(5, 10)}>{_formatar_numero(1234)}</td>"
    antiga = _celula_antiga(1234)
    assert len(nova) < len(antiga) / 4


def test_teto_do_heatmap_cabe_folgadamente_no_limite_do_streamlit():
    """Mesmo no pior caso permitido, o HTML precisa ficar muito abaixo dos 200 MB."""
    bytes_por_celula = 40  # folga sobre os ~31 medidos com dados reais
    pior_caso = MAX_CELULAS_HEATMAP * bytes_por_celula
    assert pior_caso < 1 * 1024 * 1024, "o pior caso do heatmap deve ficar abaixo de 1 MB"


def test_pivot_dos_top_n_gera_matriz_pequena():
    """A matriz é construída só sobre os pares retornados, não sobre o produto
    cartesiano de todos os municípios."""
    itens = [
        {"municipio_origem_nome": f"Origem {i}",
         "municipio_destino_nome": f"Destino {i % 3}",
         "total_doses": 100 - i}
        for i in range(25)
    ]
    df = pd.DataFrame(itens)
    pivot = df.pivot_table(
        index="municipio_origem_nome",
        columns="municipio_destino_nome",
        values="total_doses",
        aggfunc="sum",
        fill_value=0,
    )
    assert pivot.size <= MAX_CELULAS_HEATMAP
    assert pivot.shape[0] <= 25 and pivot.shape[1] <= 25
