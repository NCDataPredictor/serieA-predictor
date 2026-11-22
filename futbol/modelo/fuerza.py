"""Fuerza de ataque y defensa por equipo: Poisson con decaimiento temporal (Maher / Dixon-Coles).

Se ajusta por máxima verosimilitud con iteraciones de punto fijo (sin scipy):
    goles_local ~ Poisson(mu · loc · att[L] · def[V]),  goles_visit ~ Poisson(mu · att[V] · def[L])
Cada partido pesa exp(-ln2 · días / VIDA_MEDIA_DIAS). Los goles "efectivos" mezclan xG y goles cuando hay xG
(README §3.1). La ρ de Dixon-Coles (corrección de 0-0, 1-0, 0-1, 1-1) se estima aparte y se reporta: la
simulación minuto a minuto ya mete dependencia entre equipos con el multiplicador gamma común; si el backtest
muestra empates subestimados, se calibra ahí.

Los equipos con pocos partidos se encogen hacia 1,0 con un pseudo-partido de peso `prior_n` (los ascendidos
deberían empezar por debajo: `prior_ascendidos`).
"""
import math
from datetime import date

from . import params as P


def _goles_ef(st):
    g = st["goles"]
    if st.get("xg") is not None:
        return P.PESO_XG * st["xg"] + (1 - P.PESO_XG) * g
    return g


def ajustar(partidos, fecha_ref, prior_n=3.0, ascendidos=(), prior_ascendidos=(0.85, 1.12), iters=60):
    ref = date.fromisoformat(fecha_ref[:10])
    eqs = sorted({p["local"] for p in partidos} | {p["visitante"] for p in partidos})
    att = {e: 1.0 for e in eqs}
    dfn = {e: 1.0 for e in eqs}
    prior = {e: (prior_ascendidos if e in ascendidos else (1.0, 1.0)) for e in eqs}
    filas = []
    for p in partidos:
        dias = (ref - date.fromisoformat(p["fecha"][:10])).days
        if dias < 0:
            continue
        w = math.exp(-math.log(2) * dias / P.VIDA_MEDIA_DIAS)
        L, V = p["local"], p["visitante"]
        filas.append((L, V, _goles_ef(p["equipos"][L]), _goles_ef(p["equipos"][V]), w))
    if not filas:
        return {"mu": 1.3, "localia": P.LOCALIA_GOLES, "att": att, "def": dfn, "rho": 0.0, "n": 0}
    sw = sum(f[4] for f in filas)
    mu = sum((f[2] + f[3]) * f[4] for f in filas) / (2 * sw)
    loc = P.LOCALIA_GOLES
    for _ in range(iters):
        # ataque
        num = {e: prior_n * prior[e][0] for e in eqs}
        den = {e: prior_n for e in eqs}
        for L, V, gl, gv, w in filas:
            num[L] += w * gl
            den[L] += w * mu * loc * dfn[V]
            num[V] += w * gv
            den[V] += w * mu * dfn[L]
        att = {e: num[e] / den[e] for e in eqs}
        # defensa
        num = {e: prior_n * prior[e][1] for e in eqs}
        den = {e: prior_n for e in eqs}
        for L, V, gl, gv, w in filas:
            num[V] += w * gl
            den[V] += w * mu * loc * att[L]
            num[L] += w * gv
            den[L] += w * mu * att[V]
        dfn = {e: num[e] / den[e] for e in eqs}
        # normalizar (media geométrica 1) y re-estimar mu y localía
        ga = math.exp(sum(math.log(att[e]) for e in eqs) / len(eqs))
        gd = math.exp(sum(math.log(dfn[e]) for e in eqs) / len(eqs))
        att = {e: att[e] / ga for e in eqs}
        dfn = {e: dfn[e] / gd for e in eqs}
        nl = sum(w * gl for L, V, gl, gv, w in filas)
        dl = sum(w * mu * att[L] * dfn[V] for L, V, gl, gv, w in filas)
        nv = sum(w * gv for L, V, gl, gv, w in filas)
        dv = sum(w * att[V] * dfn[L] for L, V, gl, gv, w in filas)
        # localía encogida hacia el valor de partida (pseudo-muestra de 40 partidos)
        loc = (nl / dl / (nv / dv) * sw + P.LOCALIA_GOLES * 40) / (sw + 40)
        mu = nv / dv
    rho = _rho(partidos, att, dfn, mu, loc)
    return {"mu": mu, "localia": loc, "att": att, "def": dfn, "rho": rho, "n": len(filas)}


def esperados(fz, local, visitante, neutral=False):
    """Goles esperados (local, visitante) del modelo de fuerza."""
    loc = 1.0 if neutral else fz["localia"]
    a = fz["att"].get(local, 1.0) * fz["def"].get(visitante, 1.0) * fz["mu"] * loc
    b = fz["att"].get(visitante, 1.0) * fz["def"].get(local, 1.0) * fz["mu"]
    return a, b


def _tau(x, y, l1, l2, rho):
    if x == 0 and y == 0:
        return 1 - l1 * l2 * rho
    if x == 0 and y == 1:
        return 1 + l1 * rho
    if x == 1 and y == 0:
        return 1 + l2 * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def _rho(partidos, att, dfn, mu, loc):
    """ρ de Dixon-Coles por búsqueda en rejilla (solo con goles reales, no xG)."""
    mejor, best = 0.0, -1e18
    for k in range(-20, 11):
        rho = k / 100
        ll = 0.0
        for p in partidos:
            L, V = p["local"], p["visitante"]
            x, y = p["equipos"][L]["goles"], p["equipos"][V]["goles"]
            if x > 1 or y > 1:
                continue
            l1 = mu * loc * att.get(L, 1) * dfn.get(V, 1)
            l2 = mu * att.get(V, 1) * dfn.get(L, 1)
            t = _tau(x, y, l1, l2, rho)
            if t <= 0:
                ll = -1e18
                break
            ll += math.log(t)
        if ll > best:
            best, mejor = ll, rho
    return mejor
