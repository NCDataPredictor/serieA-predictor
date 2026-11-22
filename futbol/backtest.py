"""Backtest jornada a jornada: el modelo predice cada partido ya jugado usando SOLO lo que se sabía antes.

    python -m futbol.backtest serie_a                       # temporada actual, desde la jornada 4
    python -m futbol.backtest serie_a --desde 2 --sims 2000 --temporada 2026-27
    python -m futbol.backtest serie_a --sin-alineacion      # como en la previa (sin XI oficial)

Por defecto cada partido se simula con la alineación oficial (es lo que habrá 30-45 min antes, cuando se
publican los picks de jugadores). Mide:

  resultado   % de acierto del favorito 1X2, log loss y Brier frente a 1/3-1/3-1/3, empates simulados vs reales
  líneas      para goles, córners, amarillas, remates, a puerta, faltas, fueras de lugar (partido y equipo):
              % de acierto del lado más probable en líneas fijas, calibración por rango de probabilidad,
              % de resultados reales fuera del p10-p90 simulado (debería ser ~10% por cada lado)
  jugadores   remates, a puerta, faltas recibidas/cometidas, pases y atajadas de los titulares: calibración de
              P(≥1), P(≥2)... y % de acierto del lado más probable, con y sin suplente de oro

Sin cuotas históricas (football-data está bloqueado en la red de Nicolas) todavía no se mide frente a la casa ni
en unidades: eso es lo siguiente cuando haya cuotas de cierre.
Salida: futbol/<liga>/backtest/resumen.json (+ filas por partido en filas.json).
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from futbol import build_site_futbol as B  # noqa: E402
from futbol.modelo import base, contexto, fuerza, jugadores, simular  # noqa: E402
from futbol.modelo import params as P  # noqa: E402

LINEAS = {"goles": [1.5, 2.5, 3.5], "corners": [8.5, 9.5, 10.5], "amarillas": [3.5, 4.5, 5.5],
          "remates": [22.5, 24.5, 26.5], "remates_puerta": [7.5, 8.5, 9.5], "faltas": [22.5, 24.5, 26.5],
          "offsides": [2.5, 3.5]}
LINEAS_EQ = {"goles": [0.5, 1.5], "corners": [3.5, 4.5, 5.5], "amarillas": [1.5, 2.5], "remates": [10.5, 12.5, 14.5],
             "remates_puerta": [3.5, 4.5], "faltas": [11.5, 12.5, 13.5], "offsides": [1.5]}
STATS_J = ["remates", "remates_puerta", "faltas_recibidas", "faltas_cometidas", "pases", "atajadas"]
CUBOS = [(0, .2), (.2, .35), (.35, .5), (.5, .65), (.65, .8), (.8, 1.01)]


def _sim_partido(liga, p, hist, sims, con_alineacion):
    cfg = B.LIGAS[liga]
    L, V = p["local"], p["visitante"]
    partido = {"id": "bt-" + p["id"], "match": {"fecha": p["fecha"], "local": L, "visitante": V, "neutral": False},
               "contexto": {"arbitro": p.get("arbitro")}, "bajas": {}}
    if con_alineacion:
        al = {"estado": "oficial"}
        for t in (L, V):
            js = p["jugadores"].get(t, [])
            al[t] = {"titulares": [j["id"] for j in js if j.get("titular")],
                     "banco": [j["id"] for j in js if not j.get("titular")]}
        partido["alineaciones"] = al
    db = base.construir(hist, cfg["temporada"], hasta=p["fecha"], temporada_ant=cfg["anterior"])
    eq_act = {t for x in db["partidos"] if x["temporada"] == cfg["temporada"] for t in (x["local"], x["visitante"])}
    eq_ant = {t for x in db["partidos"] if x["temporada"] == cfg["anterior"] for t in (x["local"], x["visitante"])}
    fz = fuerza.ajustar(db["partidos"], p["fecha"], ascendidos=(eq_act - eq_ant) if eq_ant else set(), temporada=cfg["temporada"])
    ctx = contexto.armar(db, lambda a, b, n: fuerza.esperados(fz, a, b, n), partido)
    prep = {t: jugadores.preparar_equipo(db, partido, t) for t in (L, V)}
    eqs = {}
    for t in (L, V):
        mult, _ = jugadores.ajustes_bajas(prep[t], ctx["esperado"][t])
        eqs[t] = simular.Equipo(prep[t], ctx["esperado"][t], ctx["perfiles"][t], ctx["cruce"][t], mult, ctx["arbitro"], bool(ctx["derbi"]))
    sim = simular.simular(partido["id"], eqs[L], eqs[V], N=sims)
    return sim, eqs


def _logloss(p, k):
    return -math.log(max(1e-9, p[k]))


def correr(liga, temporada, desde, sims, con_alineacion, limite=None, ejemplo=False):
    hist = B.cargar(os.path.join(RAIZ, "futbol", liga, "historico", "*.json"))
    hist = [p for p in hist if bool(p.get("ejemplo")) == ejemplo]
    objetivo = [p for p in hist if p["temporada"] == temporada and (p.get("jornada") or 99) >= desde]
    objetivo.sort(key=lambda p: p["fecha"])
    if limite:
        objetivo = objetivo[:limite]
    filas = []
    acc = defaultdict(list)          # (mercado) -> [(p_over, real_over)]
    fuera = defaultdict(lambda: [0, 0, 0])   # stat -> [bajo p10, sobre p90, n]
    res1x2 = []
    for n, p in enumerate(objetivo, 1):
        L, V = p["local"], p["visitante"]
        sim, eqs = _sim_partido(liga, p, hist, sims, con_alineacion)
        gl, gv = sim["goles"]
        pr = [float((gl > gv).mean()), float((gl == gv).mean()), float((gl < gv).mean())]
        rl, rv = p["equipos"][L]["goles"], p["equipos"][V]["goles"]
        k = 0 if rl > rv else (1 if rl == rv else 2)
        res1x2.append({"p": pr, "k": k})
        fila = {"id": p["id"], "jornada": p.get("jornada"), "1x2": [round(x, 3) for x in pr], "real": [rl, rv]}
        tl, tv = sim["team"]
        for s, lineas in LINEAS.items():
            if s not in p["equipos"][L]:
                continue
            real = p["equipos"][L][s] + p["equipos"][V][s]
            x = tl[s] + tv[s]
            for li in lineas:
                acc[f"partido:{s}:{li}"].append((float((x > li).mean()), real > li))
            q10, q90 = np.percentile(x, [10, 90])
            fuera[s][0] += real < q10
            fuera[s][1] += real > q90
            fuera[s][2] += 1
            for t_i, t in enumerate((L, V)):
                xe = sim["team"][t_i][s]
                re = p["equipos"][t][s]
                for li in LINEAS_EQ.get(s, []):
                    acc[f"equipo:{s}:{li}"].append((float((xe > li).mean()), re > li))
        # jugadores titulares (props): calibración de P(≥k)
        for t_i, t in enumerate((L, V)):
            reales = {j["id"]: j for j in p["jugadores"].get(t, [])}
            e = eqs[t]
            J = sim["jug"][t_i]
            entra, sale, repl, titular = sim["lineups"][t_i]
            for j_i, x in enumerate(e.jug):
                r = reales.get(x["id"])
                if not r or not r.get("titular") or not titular[:, j_i].any():
                    continue
                es_por = x["grupo"] == "POR"
                for s in STATS_J:
                    if (s == "atajadas") != es_por or (s != "atajadas" and s not in r):
                        continue
                    if s == "atajadas":
                        continue   # el histórico normalizado aún no trae atajadas por jugador
                    v = J[s][titular[:, j_i], j_i]
                    real_v = r.get(s, 0)
                    ks = [5, 15, 25, 35, 45, 55] if s == "pases" else [1, 2, 3]
                    for kk in ks:
                        acc[f"jugador:{s}:{kk - 0.5}"].append((float((v >= kk).mean()), real_v >= kk))
        filas.append(fila)
        if n % 10 == 0:
            print(f"  {n}/{len(objetivo)}")
    return resumen(res1x2, acc, fuera, len(objetivo)), filas


def resumen(res1x2, acc, fuera, n):
    out = {"partidos": n, "version": P.MODEL_VERSION}
    if res1x2:
        ll = sum(_logloss(r["p"], r["k"]) for r in res1x2) / len(res1x2)
        br = sum(sum((r["p"][i] - (1 if i == r["k"] else 0)) ** 2 for i in range(3)) for r in res1x2) / len(res1x2)
        acierto = sum(1 for r in res1x2 if max(range(3), key=lambda i: r["p"][i]) == r["k"]) / len(res1x2)
        out["1x2"] = {"acierto_favorito": round(acierto, 3), "log_loss": round(ll, 4), "log_loss_uniforme": round(math.log(3), 4),
                      "brier": round(br, 4), "empates_sim": round(sum(r["p"][1] for r in res1x2) / len(res1x2), 3),
                      "empates_reales": round(sum(1 for r in res1x2 if r["k"] == 1) / len(res1x2), 3),
                      "locales_sim": round(sum(r["p"][0] for r in res1x2) / len(res1x2), 3),
                      "locales_reales": round(sum(1 for r in res1x2 if r["k"] == 0) / len(res1x2), 3)}
    mk = {}
    for k, v in sorted(acc.items()):
        ps = np.array([a for a, _ in v])
        ys = np.array([b for _, b in v], dtype=float)
        lado_ok = float(((ps >= 0.5) == (ys > 0.5)).mean())
        ll = float(-np.mean(ys * np.log(np.clip(ps, 1e-6, 1)) + (1 - ys) * np.log(np.clip(1 - ps, 1e-6, 1))))
        base_rate = ys.mean()
        ll0 = float(-(base_rate * math.log(max(1e-6, base_rate)) + (1 - base_rate) * math.log(max(1e-6, 1 - base_rate)))) if 0 < base_rate < 1 else 0.0
        mk[k] = {"n": len(v), "acierto_lado": round(lado_ok, 3), "p_media": round(float(ps.mean()), 3),
                 "real": round(float(base_rate), 3), "log_loss": round(ll, 4), "log_loss_tasa_base": round(ll0, 4)}
    out["mercados"] = mk
    # calibración agregada por tipo de mercado
    cal = {}
    for tipo in ("partido", "equipo", "jugador"):
        pares = [x for k, v in acc.items() if k.startswith(tipo + ":") for x in v]
        filas = []
        for a, b in CUBOS:
            sel = [(p, y) for p, y in pares if a <= p < b]
            if sel:
                filas.append({"rango": f"{int(a * 100)}-{int(min(b, 1) * 100)}%", "n": len(sel),
                              "p_media": round(sum(p for p, _ in sel) / len(sel), 3),
                              "real": round(sum(1 for _, y in sel if y) / len(sel), 3)})
        # acierto de los "picks" del modelo: lado más probable con p ≥ 60%
        fuertes = [(p, y) for p, y in pares if p >= 0.6 or p <= 0.4]
        ok = sum(1 for p, y in fuertes if (p >= 0.6) == bool(y))
        cal[tipo] = {"calibracion": filas, "lado_fuerte_n": len(fuertes),
                     "lado_fuerte_acierto": round(ok / len(fuertes), 3) if fuertes else None}
    out["calibracion"] = cal
    out["fuera_p10_p90"] = {s: {"bajo_p10": round(v[0] / v[2], 3), "sobre_p90": round(v[1] / v[2], 3), "n": v[2]}
                            for s, v in fuera.items() if v[2]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("liga", choices=list(B.LIGAS))
    ap.add_argument("--temporada")
    ap.add_argument("--desde", type=int, default=4)
    ap.add_argument("--sims", type=int, default=2000)
    ap.add_argument("--limite", type=int)
    ap.add_argument("--sin-alineacion", action="store_true")
    ap.add_argument("--ejemplo", action="store_true", help="usar la liga sintética de ejemplo (solo para probar el script)")
    a = ap.parse_args()
    temp = a.temporada or B.LIGAS[a.liga]["temporada"]
    res, filas = correr(a.liga, temp, a.desde, a.sims, not a.sin_alineacion, a.limite, a.ejemplo)
    res.update({"temporada": temp, "desde_jornada": a.desde, "sims": a.sims, "con_alineacion": not a.sin_alineacion})
    d = os.path.join(RAIZ, "futbol", a.liga, "backtest")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "resumen.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(d, "filas.json"), "w", encoding="utf-8") as fh:
        json.dump(filas, fh, ensure_ascii=False)
    print(json.dumps({k: res[k] for k in ("partidos", "1x2", "fuera_p10_p90") if k in res}, ensure_ascii=False, indent=1))
    print(json.dumps(res["calibracion"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
