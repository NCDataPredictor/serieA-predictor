"""Simula los partidos de una liga y escribe la web: docs/<liga-web>/data/.

    python -m futbol.build_site_futbol serie_a                 # todos los partidos de futbol/serie_a/partidos/
    python -m futbol.build_site_futbol serie_a 2026-11-29      # solo los de esa fecha
    python -m futbol.build_site_futbol serie_a --sims 5000     # menos simulaciones (pruebas)

Entradas (ver futbol/datos/FORMATO.md):
  futbol/<liga>/historico/*.json   partidos jugados, normalizados (los escriben los descargadores de futbol/datos/)
  futbol/<liga>/partidos/*.json    un JSON por partido a predecir (README §7.4): alineaciones, bajas, árbitro, cuotas

Salida:
  docs/<liga-web>/data/index.json   resumen ligero de la jornada (lo lee también la portada)
  docs/<liga-web>/data/<id>.json    todo el partido: contexto, mercados, tramos, jugadores, bajas, picks
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from comun import mercado as MK  # noqa: E402
from futbol.modelo import base, contexto, fuerza, jugadores, mercados, simular  # noqa: E402
from futbol.modelo import params as P  # noqa: E402

LIGAS = {"serie_a": {"web": "serie-a", "nombre": "Serie A", "temporada": "2026-27", "anterior": "2025-26"}}


def cargar(patron):
    out = []
    for f in sorted(glob.glob(patron)):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        out.extend(d if isinstance(d, list) else [d])
    return out


def predecir(liga, partido, historico, sims):
    cfg = LIGAS[liga]
    m = partido["match"]
    db = base.construir(historico, cfg["temporada"], hasta=m["fecha"], temporada_ant=cfg["anterior"])
    # ascendidos: juegan esta temporada pero no estaban en la anterior de la liga (si hay datos de la anterior)
    eq_act = {t for p in db["partidos"] if p["temporada"] == cfg["temporada"] for t in (p["local"], p["visitante"])}
    eq_ant = {t for p in db["partidos"] if p["temporada"] == cfg["anterior"] for t in (p["local"], p["visitante"])}
    ascendidos = set(partido.get("ascendidos", ())) | ((eq_act - eq_ant) if eq_ant else set())
    fz = fuerza.ajustar(db["partidos"], m["fecha"], ascendidos=ascendidos, temporada=cfg["temporada"])
    ctx = contexto.armar(db, lambda a, b, neutral: fuerza.esperados(fz, a, b, neutral), partido)
    L, V = m["local"], m["visitante"]
    prep = {t: jugadores.preparar_equipo(db, partido, t) for t in (L, V)}
    mult = {}
    bajas_det = {}
    cambios_cs = {}
    for t in (L, V):
        mult[t], bajas_det[t] = jugadores.ajustes_bajas(prep[t], ctx["esperado"][t])
        cambios_cs[t] = jugadores.companeros_con_sin(prep[t])
    derbi = bool(ctx["derbi"])
    eqs = {t: simular.Equipo(prep[t], ctx["esperado"][t], ctx["perfiles"][t], ctx["cruce"][t], mult[t], ctx["arbitro"], derbi)
           for t in (L, V)}
    sim = simular.simular(partido.get("id") or f'{m["fecha"]}-{L}-{V}', eqs[L], eqs[V], N=sims)
    res = {
        "id": partido.get("id") or f'{m["fecha"]}-{L}-{V}',
        "ejemplo": bool(partido.get("ejemplo")),
        "match": m, "contexto_partido": partido.get("contexto", {}),
        "modelo": {"version": P.MODEL_VERSION, "ascendidos": sorted(ascendidos), "sims": sim["N"], "fuerza": {"mu": round(fz["mu"], 3), "localia": round(fz["localia"], 3),
                   "rho": fz["rho"], "att": {t: round(fz["att"].get(t, 1), 3) for t in (L, V)},
                   "def": {t: round(fz["def"].get(t, 1), 3) for t in (L, V)}}, "n_historico": db["n_partidos"]},
        "partido": mercados.partido(sim, L, V),
        "equipos": {t: mercados.equipo(sim, i, t, eqs[t].esp) for i, t in enumerate((L, V))},
        "tramos_sim": {t: mercados.tramos(sim, i) for i, t in enumerate((L, V))},
        "tramos_hist": ctx["tramos_hist"],
        "perfiles": {t: {s: [round(x, 4) for x in v] for s, v in ctx["perfiles"][t].items()} for t in (L, V)},
        "factores": ctx["factores"],
        "arbitro": ctx["arbitro"], "derbi": ctx["derbi"], "estilos": ctx["estilos"], "cruce": ctx["cruce"],
        "h2h": ctx["h2h"], "forma": ctx["forma"], "liga": ctx["liga"],
        "alineacion": {t: {"estado": prep[t]["estado_alineacion"],
                           "xi": [next(x["nombre"] for x in prep[t]["jugadores"] if x["id"] == k) for k in prep[t]["xi"]]} for t in (L, V)},
        "bajas": {t: {"lista": [{k: v for k, v in b.items() if not k.startswith("_") and k != "con_sin"} for b in prep[t]["bajas"]],
                      "efecto_equipo": bajas_det[t], "companeros": cambios_cs[t]} for t in (L, V)},
        "jugadores": {t: mercados.jugadores(sim, i, eqs[t]) for i, t in enumerate((L, V))},
    }
    res["picks"] = picks(res, partido, sim, eqs)
    return res


STATS_PICK_EQUIPO = ("goles", "corners", "amarillas", "remates", "remates_puerta", "faltas", "offsides")


def _candidato(out, base, p_over, c_over, c_under):
    """Añade los lados que pasan los filtros: mezcla con la casa (MKT_W), p ≥ MIN_P, EV ≥ VALUE_EV."""
    p_casa = MK.sin_margen([c_over, c_under]) if c_over and c_under else None
    if not p_casa:
        return   # sin cuota a los dos lados no hay precio sin margen: no es pick (regla del proyecto)
    for lado, p_mod, cuota, pc in (("over", p_over, c_over, p_casa[0]), ("under", 1 - p_over, c_under, p_casa[1])):
        p = MK.mezclar(p_mod, pc, P.MKT_W)
        e = MK.ev(p, cuota)
        if p >= P.MIN_P and e >= P.VALUE_EV:
            out.append({**base, "lado": lado, "cuota": cuota, "p_modelo": round(p_mod, 3), "p_casa": round(pc, 3),
                        "p": round(p, 3), "ev": round(e, 3)})


def picks(res, partido, sim, eqs):
    """Picks con cuota real: props de jugador (incluidas atajadas del portero) y mercados de equipo y de partido.

    Props: `partido["props"] = {"Jugador": {"remates_puerta": [[línea, over, under, suplente_oro?], ...]}}`; con
    suplente de oro la prob. del modelo es la del titular + su reemplazo (condicionada a que sea titular).
    Equipo: `partido["cuotas"]["equipo"] = [{"ambito": "total|local|visitante", "stat": "corners", "linea": 9.5,
    "over": 1.85, "under": 1.95, "casa": "Betano"}]`. La probabilidad sale de las simulaciones para la línea exacta.
    """
    import numpy as np
    m = res["match"]
    L, V = m["local"], m["visitante"]
    out = []
    # ---- jugadores
    idx = {}
    for t_i, t in enumerate((L, V)):
        for j_i, x in enumerate(eqs[t].jug):
            idx[x["nombre"]] = (t_i, t, j_i)
    for nombre, mk in (partido.get("props") or {}).items():
        if nombre not in idx:
            continue
        t_i, t, j_i = idx[nombre]
        J = sim["jug"][t_i]
        entra, sale, repl, titular = sim["lineups"][t_i]
        juega = sim["minutos"][t_i][:, j_i] > 0
        for stat, lineas in mk.items():
            if stat not in J:
                continue
            x = J[stat][:, j_i]
            for fila in lineas:
                linea, c_over = fila[0], fila[1]
                c_under = fila[2] if len(fila) > 2 else None
                oro = bool(fila[3]) if len(fila) > 3 else False
                if oro and titular[:, j_i].any():
                    r_i = repl[:, j_i].astype(np.int64)
                    otro = np.where(r_i >= 0, np.take_along_axis(J[stat], np.maximum(r_i, 0)[:, None], 1)[:, 0], 0)
                    v = (x + otro)[titular[:, j_i]]
                else:
                    v = x[juega]
                if v.size == 0:
                    continue
                _candidato(out, {"tipo": "jugador", "jugador": nombre, "equipo": t, "stat": stat, "linea": linea,
                                 "suplente_oro": oro}, float((v > linea).mean()), c_over, c_under)
    # ---- equipo y partido
    for c in (partido.get("cuotas") or {}).get("equipo") or []:
        s = c.get("stat")
        if s not in STATS_PICK_EQUIPO:
            continue
        tl, tv = sim["team"][0][s], sim["team"][1][s]
        x = {"total": tl + tv, "local": tl, "visitante": tv}.get(c.get("ambito", "total"))
        if x is None:
            continue
        quien = {"total": "partido", "local": L, "visitante": V}[c.get("ambito", "total")]
        _candidato(out, {"tipo": "equipo", "jugador": quien, "equipo": quien, "stat": s, "linea": c["linea"],
                         "casa": c.get("casa"), "suplente_oro": False}, float((x > c["linea"]).mean()), c.get("over"), c.get("under"))
    out.sort(key=lambda x: -x["ev"] * x["p"])
    por_j = {}
    final = []
    for x in out:
        por_j[x["jugador"]] = por_j.get(x["jugador"], 0) + 1
        if por_j[x["jugador"]] <= P.MAX_PICKS_JUGADOR:
            final.append(x)
    return final[:P.MAX_PICKS_JORNADA]


def resumen(res):
    m = res["match"]
    L, V = m["local"], m["visitante"]
    pa = res["partido"]
    return {"id": res["id"], "fecha": m["fecha"], "hora_local": m.get("hora_local"), "hora_bogota": m.get("hora_bogota"),
            "jornada": m.get("jornada"), "local": L, "visitante": V, "estadio": m.get("estadio"), "derbi": res["derbi"],
            "arbitro": res["arbitro"].get("nombre"), "1x2": pa["1x2"], "goles": pa["total_goles"]["dist"]["media"],
            "over25": next(p for l, p in pa["total_goles"]["over"] if l == 2.5), "ambos": pa["ambos_marcan"],
            "corners": pa["totales"]["corners"]["dist"]["media"], "amarillas": pa["totales"]["amarillas"]["dist"]["media"],
            "marcador": pa["marcadores"][0], "n_picks": len(res["picks"]), "ejemplo": res["ejemplo"],
            "alineacion": {t: res["alineacion"][t]["estado"] for t in (L, V)},
            "bajas": {t: len(res["bajas"][t]["lista"]) for t in (L, V)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("liga", choices=list(LIGAS))
    ap.add_argument("fecha", nargs="?")
    ap.add_argument("--sims", type=int, default=P.SIMS)
    a = ap.parse_args()
    cfg = LIGAS[a.liga]
    hist = cargar(os.path.join(RAIZ, "futbol", a.liga, "historico", "*.json"))
    partidos = cargar(os.path.join(RAIZ, "futbol", a.liga, "partidos", "*.json"))
    if a.fecha:
        partidos = [p for p in partidos if p["match"]["fecha"] == a.fecha]
    outdir = os.path.join(RAIZ, "docs", cfg["web"], "data")
    os.makedirs(outdir, exist_ok=True)
    idx_path = os.path.join(outdir, "index.json")
    idx = {"partidos": []}
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            idx = json.load(fh)
    viejos = {p["id"]: p for p in idx.get("partidos", [])}
    for p in partidos:
        res = predecir(a.liga, p, hist, a.sims)
        with open(os.path.join(outdir, res["id"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
        viejos[res["id"]] = resumen(res)
        print(f'{res["id"]}: 1X2 {res["partido"]["1x2"]}  goles {res["partido"]["total_goles"]["dist"]["media"]}  picks {len(res["picks"])}')
    lista = sorted(viejos.values(), key=lambda x: (x["fecha"], x.get("hora_local") or "", x["id"]))
    idx = {"liga": cfg["nombre"], "temporada": cfg["temporada"], "version": P.MODEL_VERSION,
           "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "ejemplo": any(x.get("ejemplo") for x in lista), "partidos": lista}
    with open(idx_path, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
