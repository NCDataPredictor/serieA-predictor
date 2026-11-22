"""Simulación Monte Carlo minuto a minuto de un partido de fútbol (README §3.2).

Por cada simulación y cada minuto (1..90; el añadido va dentro de los tramos 31-45+ y 76-90+):

  1. Quién está en el campo: XI (con su prob. de ser titular), minuto de salida de cada titular, quién entra por
     él (el suplente que más veces lo reemplazó o uno de su línea), máx. 5 cambios, y expulsados fuera.
  2. Intensidad de cada equipo y estadística en ese minuto:
         λ(m) = esperado del partido × perfil del tramo de m (la "distribución" del equipo frente al rival)
                × multiplicador gamma del partido (común + propio: sobredispersión)
                × estado del marcador (pierde / empata / gana) × rojas (propias y del rival)
  3. Los eventos se generan POR JUGADOR en el campo (Poisson con su parte del volumen): remates, faltas
     cometidas y pases. Remates → a puerta (precisión del jugador) → gol (conversión del equipo). Las faltas de
     un equipo son las faltas recibidas del otro (reparto multinomial entre sus jugadores). Cada falta puede
     ser amarilla (según el jugador, el árbitro y el derbi); segunda amarilla o roja directa = fuera.
     Córners y fueras de lugar son de equipo.
  Así equipo y jugadores quedan correlacionados: si el equipo va perdiendo y remata más, sus delanteros también.

Suplente de oro: para cada titular se guarda quién entró por él; la estadística "con suplente de oro" es la
del titular + la del que lo reemplazó (lo que el suplente hace después de entrar).
"""
import zlib

import numpy as np

from . import params as P
from .base import tramo_de

TRAMO_DE_MIN = np.array([tramo_de(m) for m in range(1, P.MINUTOS + 1)])
STATS_J_SIM = ["remates", "remates_puerta", "faltas_cometidas", "faltas_recibidas", "pases", "amarillas", "goles", "atajadas"]


def _semilla(pid):
    return zlib.crc32(pid.encode()) & 0x7FFFFFFF


class Equipo:
    """Arreglos de un equipo para la simulación."""

    def __init__(self, prep, esperado, perfil, cruce, mult_bajas, arb, derbi):
        self.cod = prep["equipo"]
        self.jug = prep["jugadores"]
        self.n = len(self.jug)
        idx = {x["id"]: i for i, x in enumerate(self.jug)}
        self.idx = idx
        self.xi = [idx[k] for k in prep["xi"] if k in idx]
        self.esp = dict(esperado)
        for s, m in mult_bajas.items():
            if s in self.esp:
                self.esp[s] *= m
        self.perfil = {s: np.array(v) for s, v in perfil.items()}
        t = lambda s: np.array([max(1e-4, x["tasas90"][s]) for x in self.jug])
        zona = cruce["ratio_zona_rival"]
        mz = np.array([zona.get(x["lado"], 1.0) ** 0.5 for x in self.jug])
        self.w = {"remates": t("remates") * mz, "faltas_cometidas": t("faltas_cometidas"),
                  "faltas_recibidas": t("faltas_recibidas"), "pases": t("pases")}
        # precisión de cada jugador, centrada para que el equipo dé su esperado de remates a puerta
        acc_raw = np.array([(x["tasas90"]["remates_puerta"] + 0.1) / (x["tasas90"]["remates"] + 0.3) for x in self.jug])
        w_xi = self.w["remates"][self.xi] if self.xi else self.w["remates"]
        acc_xi = acc_raw[self.xi] if self.xi else acc_raw
        acc_eq = self.esp["remates_puerta"] / max(0.1, self.esp["remates"])
        acc_media = float((acc_xi * w_xi).sum() / max(1e-9, w_xi.sum()))
        self.acc = np.clip(acc_raw * acc_eq / max(1e-6, acc_media), 0.05, 0.9)
        self.conv = min(0.8, self.esp["goles"] / max(0.2, self.esp["remates_puerta"]))
        # amarillas: escala para que el equipo dé su esperado (las que no vienen de faltas aparte)
        apf = np.array([x["amarilla_por_falta"] for x in self.jug])
        wf = self.w["faltas_cometidas"][self.xi] if self.xi else self.w["faltas_cometidas"]
        apf_xi = apf[self.xi] if self.xi else apf
        sin_falta = P.AMARILLA_SIN_FALTA * arb["mult_amarillas"] * (P.DERBI_TARJETAS if derbi else 1.0)
        objetivo = max(0.3, self.esp["amarillas"] - sin_falta)
        por_falta_media = float((apf_xi * wf).sum() / max(1e-9, wf.sum()))
        self.p_am = np.clip(apf * objetivo / max(1e-6, por_falta_media * self.esp["faltas"]), 0.0, 0.6)
        self.am_sin_falta = sin_falta
        self.p_roja = P.ROJA_DIRECTA_POR_FALTA * arb.get("mult_rojas", 1.0) * (P.DERBI_TARJETAS if derbi else 1.0)
        self.salida = [x["salida"] for x in self.jug]
        self.p_tit = np.array([x["p_titular"] for x in self.jug])
        self.es_por = np.array([x["grupo"] == "POR" for x in self.jug])
        # el esperado de pases del equipo es de pases TOTALES; los de jugador se miden como ACERTADOS (FotMob)
        self.prec_pase = float(prep.get("precision_pase", 0.84))


def _alineaciones(eq, N, rng):
    """entra[N,P], sale[N,P] (juega los minutos entra < m <= sale) y reemplazo[N,P] (-1 si no salió)."""
    Pn = eq.n
    entra = np.zeros((N, Pn), dtype=np.int16)
    sale = np.zeros((N, Pn), dtype=np.int16)
    repl = np.full((N, Pn), -1, dtype=np.int16)
    titular = np.zeros((N, Pn), dtype=bool)
    xi = list(eq.xi)
    fuera = [i for i in range(Pn) if i not in xi]
    # alternativa de cada titular dudoso: el de su línea fuera del XI con más p_titular
    alt = {}
    for i in xi:
        g = eq.jug[i]["grupo"]
        cands = sorted([j for j in fuera if eq.jug[j]["grupo"] == g], key=lambda j: -eq.p_tit[j])
        alt[i] = cands[0] if cands else None
    u_tit = rng.random((N, len(xi)))
    for k, i in enumerate(xi):
        p = eq.p_tit[i] if eq.p_tit[i] > 0 else 0.9
        # el XI ya es lo más probable: la prob. de que entre la alternativa es 1 - p del titular, si hay alternativa
        no = (u_tit[:, k] > p) & (alt[i] is not None)
        titular[:, i] = ~no
        if alt[i] is not None:
            titular[no, alt[i]] = True
    # minuto de salida de cada titular
    sal = np.full((N, Pn), 90, dtype=np.int16)
    u90 = rng.random((N, Pn))
    z = rng.standard_normal((N, Pn))
    for i in range(Pn):
        s = eq.salida[i]
        if eq.jug[i]["grupo"] == "POR":
            continue   # el portero casi nunca sale
        m = np.clip(np.round(s["media"] + s["de"] * z[:, i]), 30, 89).astype(np.int16)
        sal[:, i] = np.where(u90[:, i] < s["p90"], 90, m)
    sal = np.where(titular, sal, 0)
    # pesos de cada suplente para entrar por cada titular
    pesos = np.zeros((Pn, Pn))
    for i, x in enumerate(eq.jug):
        for j, y in enumerate(eq.jug):
            if i == j:
                continue
            if (x["grupo"] == "POR") != (y["grupo"] == "POR"):
                continue   # un portero solo entra por otro portero
            w = max(0.02, y["p_entra"]) * (1.0 if y["grupo"] == x["grupo"] else 0.2)
            w += 2.0 * x["reemplazado_por"].get(y["id"], 0) / max(1, sum(x["reemplazado_por"].values()))
            pesos[i, j] = w
    u_rep = rng.random((N, 5))
    for s_ in range(N):
        tit = np.flatnonzero(titular[s_])
        entra[s_, tit] = 0
        sale[s_, tit] = sal[s_, tit]
        salen = [i for i in tit if sal[s_, i] < 90]
        salen.sort(key=lambda i: sal[s_, i])
        usados = set(tit.tolist())
        cambios = 0
        for i in salen:
            if cambios >= 5:
                sale[s_, i] = 90
                continue
            w = pesos[i].copy()
            if usados:
                w[list(usados)] = 0
            tot = w.sum()
            if tot <= 0:
                sale[s_, i] = 90
                continue
            j = int(np.searchsorted(np.cumsum(w) / tot, u_rep[s_, cambios]))
            j = min(j, Pn - 1)
            usados.add(j)
            entra[s_, j] = sal[s_, i]
            sale[s_, j] = 90
            repl[s_, i] = j
            cambios += 1
    return entra, sale, repl, titular


def simular(pid, A, B, N=None, local_es_A=True):
    """Simula el partido. A = local, B = visitante (objetos Equipo). Devuelve los arreglos de resultados."""
    N = N or P.SIMS
    rng = np.random.default_rng(_semilla(pid))
    eqs = [A, B]
    lineups = [_alineaciones(e, N, rng) for e in eqs]
    g_comun = rng.gamma(P.GAMMA_COMUN, 1 / P.GAMMA_COMUN, N)
    g_eq = [g_comun * rng.gamma(P.GAMMA_EQUIPO, 1 / P.GAMMA_EQUIPO, N) for _ in eqs]
    sale_eff = [lu[1].copy() for lu in lineups]   # se acorta con las expulsiones
    goles = [np.zeros(N, dtype=np.int16) for _ in eqs]
    goles_ht = [None, None]
    rojas = [np.zeros(N, dtype=np.int16) for _ in eqs]
    team = [{s: np.zeros(N, dtype=np.int32) for s in P.STATS_EQUIPO} for _ in eqs]
    jug = [{s: np.zeros((N, e.n), dtype=np.int32) for s in STATS_J_SIM} for e in eqs]
    tramos = [{s: np.zeros((N, 6), dtype=np.int16) for s in P.STATS_EQUIPO} for _ in eqs]
    primer_gol = np.zeros(N, dtype=np.int8)   # 0 = nadie, 1 = local, 2 = visitante
    min_primer_gol = np.zeros(N, dtype=np.int16)

    for m in range(1, P.MINUTOS + 1):
        k = TRAMO_DE_MIN[m - 1]
        for t, e in enumerate(eqs):
            r = 1 - t
            o = eqs[r]
            entra, _, _, _ = lineups[t]
            on = (entra < m) & (sale_eff[t] >= m)
            on_r = (lineups[r][0] < m) & (sale_eff[r] >= m)
            diff = goles[t].astype(np.int16) - goles[r]
            est_idx = np.where(diff < 0, 0, np.where(diff == 0, 1, 2))
            if m < P.ESTADO_DESDE_MIN:
                est_idx = np.ones(N, dtype=np.int64)
            f_roja = (P.ROJA_PROPIO ** rojas[t]) * (P.ROJA_RIVAL ** rojas[r])
            base = g_eq[t] * f_roja

            def lam(s):
                # cada estadística toma una fracción de la gamma del partido (backtest 2026-27: con la gamma entera la
                # desviación de remates, faltas y a puerta salía ~30% mayor que la real)
                ex = P.GAMMA_EXP.get(s, 1.0)
                b_ = base if ex == 1.0 else (g_eq[t] ** ex) * f_roja
                x = e.esp[s] * e.perfil[s][k] * 6 / P.MINUTOS * b_
                if s in P.ESTADO:
                    x = x * np.array(P.ESTADO[s])[est_idx]
                return x

            # ---- remates por jugador → a puerta → gol
            w = e.w["remates"] * on
            den = w.sum(1, keepdims=True)
            den[den == 0] = 1
            lr = lam("remates")[:, None] * w / den
            rem = rng.poisson(lr)
            pue = rng.binomial(rem, e.acc[None, :])
            gol = rng.binomial(pue, e.conv)
            jug[t]["remates"] += rem
            jug[t]["remates_puerta"] += pue
            jug[t]["goles"] += gol
            # atajadas: remates a puerta que no son gol, para el portero rival que esté en el campo
            paradas = (pue.sum(1) - gol.sum(1)).astype(np.int32)
            if paradas.any():
                jug[r]["atajadas"] += paradas[:, None] * (on_r & o.es_por[None, :])
            rt, pt, gt = rem.sum(1), pue.sum(1), gol.sum(1)
            team[t]["remates"] += rt
            team[t]["remates_puerta"] += pt
            tramos[t]["remates"][:, k] += rt.astype(np.int16)
            tramos[t]["remates_puerta"][:, k] += pt.astype(np.int16)
            nuevos = gt > 0
            if nuevos.any():
                pg = nuevos & (primer_gol == 0)
                primer_gol[pg] = t + 1
                min_primer_gol[pg] = m
            goles[t] = goles[t] + gt.astype(np.int16)
            team[t]["goles"] += gt
            tramos[t]["goles"][:, k] += gt.astype(np.int16)
            # ---- pases por jugador
            w = e.w["pases"] * on
            den = w.sum(1, keepdims=True)
            den[den == 0] = 1
            pa = rng.poisson(lam("pases")[:, None] * w / den)
            jug[t]["pases"] += rng.binomial(pa, e.prec_pase)
            team[t]["pases"] += pa.sum(1)
            tramos[t]["pases"][:, k] += np.minimum(pa.sum(1), 32000).astype(np.int16)
            # ---- faltas cometidas por jugador (y recibidas por los del rival)
            # el amonestado se cuida: comete menos faltas (CAUTELA_FALTAS) y le sacan menos la segunda
            amon = jug[t]["amarillas"] > 0
            w = e.w["faltas_cometidas"] * on * np.where(amon, P.CAUTELA_FALTAS, 1.0)
            den = (e.w["faltas_cometidas"] * on).sum(1, keepdims=True)
            den[den == 0] = 1
            fc = rng.poisson(lam("faltas")[:, None] * w / den)
            jug[t]["faltas_cometidas"] += fc
            ft = fc.sum(1)
            team[t]["faltas"] += ft
            tramos[t]["faltas"][:, k] += ft.astype(np.int16)
            if ft.any():
                wr = o.w["faltas_recibidas"] * on_r
                den_r = wr.sum(1, keepdims=True)
                den_r[den_r == 0] = 1
                pr = wr / den_r
                resto = ft.astype(np.int64)
                acum = np.zeros(N)
                for j in range(o.n):
                    pj_ = np.where(1 - acum > 1e-9, pr[:, j] / np.maximum(1e-9, 1 - acum), 0)
                    x = rng.binomial(resto, np.clip(pj_, 0, 1))
                    jug[r]["faltas_recibidas"][:, j] += x
                    resto -= x
                    acum += pr[:, j]
            # ---- tarjetas: por falta (según jugador, árbitro y derbi) + las que no vienen de una falta
            am = rng.binomial(fc, e.p_am[None, :] * np.where(amon, P.CAUTELA_AMARILLA, 1.0)).astype(np.int64)
            rd = rng.binomial(fc, e.p_roja) if ft.any() else np.zeros_like(am)
            am_sf = rng.poisson(e.am_sin_falta / P.MINUTOS, N)
            if am_sf.any():
                # a un jugador en el campo, ponderado por su tendencia (y menos si ya está amonestado)
                ww = e.p_am[None, :] * on * np.where(amon, P.CAUTELA_AMARILLA, 1.0)
                dd = ww.sum(1, keepdims=True)
                dd[dd == 0] = 1
                cum = np.cumsum(ww / dd, axis=1)
                elegido = np.minimum((rng.random(N)[:, None] > cum).sum(1), e.n - 1)
                sel = am_sf > 0
                am[sel, elegido[sel]] += 1
            if am.any() or rd.any():
                self_tarjetas(t, e, m, am, rd, jug, team, tramos, rojas, sale_eff, k, N)
            # ---- córners y fueras de lugar (equipo)
            for s in ("corners", "offsides"):
                x = rng.poisson(lam(s))
                team[t][s] += x
                tramos[t][s][:, k] += x.astype(np.int16)
        if m == 45:
            goles_ht = [g.copy() for g in goles]

    minutos = []
    for t, e in enumerate(eqs):
        entra = lineups[t][0]
        minutos.append(np.clip(sale_eff[t] - entra, 0, 90))
    return {"N": N, "goles": goles, "goles_ht": goles_ht, "team": team, "jug": jug, "tramos": tramos,
            "lineups": lineups, "minutos": minutos, "rojas": rojas, "primer_gol": primer_gol,
            "min_primer_gol": min_primer_gol}


def self_tarjetas(t, e, m, am, rd, jug, team, tramos, rojas, sale_eff, k, N):
    """Suma amarillas; la segunda amarilla o la roja directa expulsan al jugador (sale en el minuto m)."""
    previas = jug[t]["amarillas"]
    nuevas = previas + am
    expulsa = ((nuevas >= 2) & (previas < 2)) | (rd > 0)
    # un expulsado ya no está en el campo: sus amarillas posteriores no cuentan (ya salió)
    jug[t]["amarillas"] = np.minimum(nuevas, 2)
    am_tot = (np.minimum(nuevas, 2) - previas).sum(1)
    team[t]["amarillas"] += am_tot
    tramos[t]["amarillas"][:, k] += am_tot.astype(np.int16)
    if expulsa.any():
        n_exp = expulsa.sum(1)
        team[t]["rojas"] += n_exp
        tramos[t]["rojas"][:, k] += n_exp.astype(np.int16)
        rojas[t] += n_exp.astype(np.int16)
        sale_eff[t] = np.where(expulsa, np.minimum(sale_eff[t], m), sale_eff[t])
