"""Cuotas decimales, margen y mezcla modelo-casa (la lección 1 del proyecto NBA, README §1.5).

Siempre cuotas decimales y nunca una cuota supuesta: si una casa no trae un mercado, ese mercado no aparece.
"""


def sin_margen(cuotas):
    """Probabilidades implícitas sin margen (normalización proporcional) de un mercado de 2 o 3 salidas."""
    inv = [1 / c for c in cuotas if c and c > 1]
    if len(inv) != len(cuotas):
        return None
    s = sum(inv)
    return [x / s for x in inv]


def mezclar(p_modelo, p_casa, w_modelo):
    """p = (1 − w)·p_casa + w·p_modelo. Sin cuota de la casa no hay mezcla (devuelve None: no es pick)."""
    if p_casa is None:
        return None
    return (1 - w_modelo) * p_casa + w_modelo * p_modelo


def ev(p, cuota):
    return p * cuota - 1


def cuota_justa(p):
    return round(1 / p, 2) if p and p > 0 else None
