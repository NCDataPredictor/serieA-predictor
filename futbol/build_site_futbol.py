"""Simula los partidos de una liga y escribe la web: docs/futbol/<liga>/data/.

    python -m futbol.build_site_futbol serie_a                 # todos los partidos de futbol/serie_a/partidos/
    python -m futbol.build_site_futbol serie_a 2026-11-29      # solo los de esa fecha
    python -m futbol.build_site_futbol serie_a --sims 5000     # menos simulaciones (pruebas)

Entradas (ver futbol/datos/FORMATO.md):
  futbol/<liga>/historico/*.json   partidos jugados, normalizados (los escriben los descargadores de futbol/datos/)
  futbol/<liga>/partidos/*.json    un JSON por partido a predecir (README §7.4): alineaciones, bajas, árbitro, cuotas

Salida:
  docs/futbol/<liga-web>/data/index.json   resumen ligero de la jornada (lo lee también la portada)
  docs/futbol/<liga-web>/data/<id>.json    todo el partido: contexto, mercados, tramos, jugadores, bajas, picks
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
    fz = fuerza.ajustar(db["partidos"], m["fecha"], ascendidos=partido.get("ascendidos", ()))
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
        "modelo": {"version": P.MODEL_VERSION, "sims": sim["N"], "fuerza": {"mu": round(fz["mu"], 3), "localia": round(fz["localia"], 3),
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
    res["picks"] = picks(res, partido)
    return res


def picks(res, partido):
    """Picks de props con cuota real: mezcla con la casa (MKT_W), EV ≥ VALUE_EV, p ≥ MIN_P, topes.

    Si la casa ofrece suplente de oro en ese mercado (`"suplente_oro": true` en la prop), la prob. del modelo es
    la del titular + su reemplazo. Sin cuotas no hay picks (regla del proyecto: nunca suponer una cuota).
    """
    out = []
    props = partido.get("props") or {}
    por_nombre = {}
    for t, js in res["jugadores"].items():
        for j in js:
            por_nombre[j["nombre"]] = (t, j)
    for nombre, mk in props.items():
        if nombre not in por_nombre:
            continue
        t, j = por_nombre[nombre]
        for stat, lineas in mk.items():
            if stat not in j["stats"]:
                continue
            st = j["stats"][stat]
            for fila in lineas:
                linea, c_over, c_under = fila[0], fila[1], fila[2] if len(fila) > 2 else None
                oro = bool(fila[3]) if len(fila) > 3 else False
                tabla = st.get("oro_over") if oro and st.get("oro_over") else st["over"]
                p_over = next((p for l, p in tabla if abs(l - linea) < 1e-6), None)
                if p_over is None:
                    continue
                p_casa = MK.sin_margen([c_over, c_under]) if c_under else None
                for lado, p_mod, cuota, pc in (("over", p_over, c_over, p_casa[0] if p_casa else None),
                                               ("under", 1 - p_over, c_under, p_casa[1] if p_casa else None)):
                    if not cuota or pc is None:
                        continue
                    p = MK.mezclar(p_mod, pc, P.MKT_W)
                    e = MK.ev(p, cuota)
                    if p >= P.MIN_P and e >= P.VALUE_EV:
                        out.append({"jugador": nombre, "equipo": t, "stat": stat, "linea": linea, "lado": lado, "cuota": cuota,
                                    "p_modelo": round(p_mod, 3), "p_casa": round(pc, 3), "p": round(p, 3), "ev": round(e, 3),
                                    "suplente_oro": oro})
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
    outdir = os.path.join(RAIZ, "docs", "futbol", cfg["web"], "data")
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
