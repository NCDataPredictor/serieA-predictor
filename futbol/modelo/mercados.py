"""De las simulaciones a los mercados: equipo, partido, tramos y jugadores (con suplente de oro)."""
import numpy as np

from . import params as P

LINEAS_EQUIPO = {
    "goles": [0.5, 1.5, 2.5, 3.5, 4.5],
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
    "amarillas": [2.5, 3.5, 4.5, 5.5, 6.5],
    "faltas": [20.5, 22.5, 24.5, 26.5, 28.5],
    "remates": [20.5, 22.5, 24.5, 26.5, 28.5],
    "remates_puerta": [6.5, 7.5, 8.5, 9.5, 10.5],
    "offsides": [2.5, 3.5, 4.5, 5.5],
    "pases": [750.5, 800.5, 850.5, 900.5, 950.5],
    "rojas": [0.5],
}
STATS_PROP = ["remates", "remates_puerta", "faltas_recibidas", "faltas_cometidas", "pases", "atajadas"]


def _r(x, d=3):
    return round(float(x), d)


def _dist(x):
    q = np.percentile(x, [10, 25, 50, 75, 90])
    return {"media": _r(x.mean(), 2), "p10": _r(q[0], 1), "p25": _r(q[1], 1), "p50": _r(q[2], 1),
            "p75": _r(q[3], 1), "p90": _r(q[4], 1)}


def _lineas_alrededor(x, paso, n=5):
    c = np.median(x)
    base = np.floor(c / paso) * paso
    return [base + paso * (i - n // 2) + 0.5 for i in range(n) if base + paso * (i - n // 2) + 0.5 > 0]


def _over(x, lineas):
    return [[_r(l, 1), _r((x > l).mean())] for l in lineas]


def partido(sim, L, V):
    gl, gv = sim["goles"]
    N = sim["N"]
    out = {"N": N}
    out["1x2"] = [_r((gl > gv).mean()), _r((gl == gv).mean()), _r((gl < gv).mean())]
    out["doble_oportunidad"] = {"1X": _r((gl >= gv).mean()), "12": _r((gl != gv).mean()), "X2": _r((gl <= gv).mean())}
    hl, hv = sim["goles_ht"]
    out["descanso_1x2"] = [_r((hl > hv).mean()), _r((hl == hv).mean()), _r((hl < hv).mean())]
    tot = gl + gv
    out["total_goles"] = {"dist": _dist(tot), "over": _over(tot, LINEAS_EQUIPO["goles"])}
    out["ambos_marcan"] = _r(((gl > 0) & (gv > 0)).mean())
    out["porteria_cero"] = {L: _r((gv == 0).mean()), V: _r((gl == 0).mean())}
    # marcadores exactos más probables
    cl = np.minimum(gl, 6).astype(np.int32)
    cv = np.minimum(gv, 6).astype(np.int32)
    tab = np.bincount(cl * 7 + cv, minlength=49) / N
    orden = np.argsort(-tab)[:8]
    out["marcadores"] = [[f"{i // 7}-{i % 7}", _r(tab[i])] for i in orden]
    # hándicap asiático simple (margen)
    marg = gl.astype(int) - gv
    out["margen"] = {str(k): _r((marg == k).mean()) for k in range(-3, 4)}
    pg = sim["primer_gol"]
    out["primer_gol"] = {L: _r((pg == 1).mean()), V: _r((pg == 2).mean()), "ninguno": _r((pg == 0).mean())}
    mg = sim["min_primer_gol"][pg > 0]
    out["minuto_primer_gol"] = _dist(mg) if mg.size else None
    # totales del partido para las demás estadísticas
    tl, tv = sim["team"]
    out["totales"] = {}
    for s in P.STATS_EQUIPO:
        x = tl[s] + tv[s]
        lineas = LINEAS_EQUIPO.get(s) or _lineas_alrededor(x, 1)
        if s in ("pases",):
            lineas = _lineas_alrededor(x, 50)
        elif s not in ("goles", "rojas"):
            lineas = _lineas_alrededor(x, 1)
        out["totales"][s] = {"dist": _dist(x), "over": _over(x, lineas)}
    # quién hace más (córners, tarjetas, remates): mercado típico de casas
    out["mas_que_rival"] = {s: [_r((tl[s] > tv[s]).mean()), _r((tl[s] == tv[s]).mean()), _r((tl[s] < tv[s]).mean())]
                            for s in ("corners", "amarillas", "remates", "remates_puerta", "faltas", "offsides")}
    return out


def equipo(sim, t, cod, esperado):
    st = sim["team"][t]
    out = {}
    for s in P.STATS_EQUIPO:
        x = st[s]
        if s == "pases":
            lineas = _lineas_alrededor(x, 25)
        elif s in ("goles", "rojas"):
            lineas = [0.5, 1.5, 2.5, 3.5] if s == "goles" else [0.5]
        else:
            lineas = _lineas_alrededor(x, 1)
        out[s] = {"esperado": _r(esperado[s], 2), "dist": _dist(x), "over": _over(x, lineas)}
    return out


def tramos(sim, t):
    """Por tramo de 15': media simulada y prob. de que haya al menos uno (goles, córners, tarjetas…)."""
    tr = sim["tramos"][t]
    return {s: {"media": [_r(v, 3) for v in tr[s].mean(0)], "p_alguno": [_r(v, 3) for v in (tr[s] > 0).mean(0)]}
            for s in P.STATS_EQUIPO}


def jugadores(sim, t, eq):
    """Props por jugador. Las probabilidades son condicionadas a que juegue (si no juega, la casa anula).

    Para titulares se da también la versión con SUPLENTE DE ORO: titular + lo que hace quien entra por él.
    """
    entra, sale, repl, titular = sim["lineups"][t]
    mins = sim["minutos"][t]
    J = sim["jug"][t]
    out = []
    for i, x in enumerate(eq.jug):
        juega = mins[:, i] > 0
        pj = juega.mean()
        if pj < 0.02:
            continue
        tit = titular[:, i]
        p_tit = tit.mean()
        rec = {"id": x["id"], "nombre": x["nombre"], "pos": x["pos"], "lado": x["lado"], "dorsal": x.get("dorsal"),
               "p_juega": _r(pj), "p_titular": _r(p_tit), "min_medio": _r(mins[juega, i].mean(), 1),
               "min_si_titular": _r(mins[tit, i].mean(), 1) if tit.any() else None,
               "p_completa": _r((sale[tit, i] >= 90).mean()) if tit.any() else None,
               "hereda_de": x.get("hereda_de"), "tasas90": x["tasas90"], "stats": {}}
        # quién suele entrar por él en las simulaciones (para explicar el suplente de oro)
        if tit.any():
            r_i = repl[tit, i]
            sale_tit = r_i >= 0
            rec["p_sustituido"] = _r(sale_tit.mean())
            if sale_tit.any():
                cnt = np.bincount(r_i[sale_tit], minlength=eq.n) / sale_tit.sum()
                top = np.argsort(-cnt)[:3]
                rec["suplentes_oro"] = [[eq.jug[j]["nombre"], _r(cnt[j])] for j in top if cnt[j] > 0.05]
        for s in STATS_PROP:
            if (s == "atajadas") != (x["grupo"] == "POR"):
                continue   # atajadas solo para porteros; los porteros no llevan el resto de props
            x_s = J[s][:, i]
            xs = x_s[juega]
            if s == "pases":
                lineas = _lineas_alrededor(xs, 5)
            else:
                kmax = int(max(1, min(8, np.percentile(xs, 97) + 1)))
                lineas = [k - 0.5 for k in range(1, kmax + 1)]
            st = {"media": _r(xs.mean(), 2), "dist": _dist(xs), "over": _over(xs, lineas)}
            if P.SUPLENTE_ORO and tit.any():
                # titular + el que entra por él (sus números son todos posteriores a su entrada)
                r_i = repl[:, i].astype(np.int64)
                otro = np.where(r_i >= 0, np.take_along_axis(J[s], np.maximum(r_i, 0)[:, None], 1)[:, 0], 0)
                comb = (x_s + otro)[tit]
                solo = x_s[tit]
                st["titular_over"] = _over(solo, lineas)
                st["oro_over"] = _over(comb, lineas)
                # cuánto aporta el suplente de oro en la línea principal (la más cercana a 50%)
                st["oro_ganancia"] = _r(max(((comb > l).mean() - (solo > l).mean()) for l in lineas))
            rec["stats"][s] = st
        am = J["amarillas"][:, i][juega]
        rec["p_amarilla"] = _r((am > 0).mean())
        g = J["goles"][:, i][juega]
        rec["p_gol"] = _r((g > 0).mean())
        out.append(rec)
    out.sort(key=lambda r: (-r["p_titular"], -r["p_juega"]))
    return out
