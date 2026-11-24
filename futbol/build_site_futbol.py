"""Simula los partidos de una liga y escribe la web: docs/<liga-web>/data/.

    python -m futbol.build_site_futbol serie_a                 # todos los partidos de futbol/serie_a/partidos/
    python -m futbol.build_site_futbol serie_a 2026-11-29      # solo los de esa fecha
    python -m futbol.build_site_futbol serie_a --sims 5000     # menos simulaciones (pruebas)
    python -m futbol.build_site_futbol serie_a --picks-ya      # publica los picks ya, sin esperar la noche anterior

Picks por jornada: se calculan siempre, pero se publican desde la noche anterior al primer partido de la jornada
(HORA_PICKS, hora de Bogotá), cuando ya están las cuotas de las casas colombianas (Betano las abre ≈2 días antes).
Desde ahí cada corrida los va actualizando con las cuotas y alineaciones nuevas; los de partidos ya empezados quedan
congelados. Un partido atrasado de una jornada vieja publica sus picks en cuanto hay cuotas.

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
from datetime import datetime, timedelta, timezone

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
    res["ult_cols"] = list(ULT_COLS)
    _recientes_jugadores(res, historico, m["fecha"])
    return res


# Últimos partidos jugados de cada jugador (para la ficha del jugador y los mini gráficos de sus líneas en la web).
# Compacto: una fila por partido con las columnas de ULT_COLS (de más viejo a más reciente).
ULT_COLS = ("fecha", "rival", "local", "min", "titular", "remates", "remates_puerta", "faltas_cometidas",
            "faltas_recibidas", "pases", "amarillas")
ULT_N = 10


def _recientes_jugadores(res, historico, fecha):
    num = lambda pid: str(pid or "").split("-")[-1]
    quiero = {num(j["id"]) for t in res["jugadores"] for j in res["jugadores"][t] if j.get("id")}
    filas = {}
    for x in historico:
        if x.get("fecha", "") >= fecha or not x.get("jugadores"):
            continue
        for t, js in x["jugadores"].items():
            rival = x["visitante"] if t == x["local"] else x["local"]
            for j in js:
                k = num(j.get("id"))
                if k not in quiero or not j.get("jugo"):
                    continue
                mins = max(0, int(round((j.get("min_sale") or 0) - (j.get("min_entra") or 0))))
                filas.setdefault(k, []).append([x["fecha"], rival, int(t == x["local"]), mins, int(bool(j.get("titular")))]
                                               + [j.get(c) for c in ULT_COLS[5:]])
    for t in res["jugadores"]:
        for j in res["jugadores"][t]:
            u = sorted(filas.get(num(j.get("id")), []), key=lambda r: r[0])
            j["ult"] = u[-ULT_N:]


STATS_PICK_EQUIPO = ("goles", "corners", "amarillas", "tarjetas", "remates", "remates_puerta", "faltas", "offsides")

# Picks de equipo con cuota real (provisional hasta tener backtest de estas reglas; ver README):
# la probabilidad que se usa mezcla la casa sin margen con la "evidencia" = media del modelo y del cumplimiento
# histórico de la línea (encogido hacia la casa). Además el modelo y el histórico deben estar a favor por separado.
EVID_W = 0.35          # peso de la evidencia (modelo + histórico) frente a la casa
HIST_K = 4             # encogimiento del % de cumplimiento hacia la casa: (aciertos + K·p_casa) / (n + K)
ERR_MIN_HIST = 0.70    # error de cuota: el histórico cumple ≥ 70%…
ERR_MAX_CASA = 0.45    # …y la casa le da ≤ 45% (sin margen)…
ERR_DIST = 0.20        # …con el promedio al menos un 20% lejos de la línea, y el modelo del mismo lado (≥ 50%)


def _historial_linea(res, s, ambito):
    """Valores de esa estadística en la temporada para juzgar una línea, con el rival en cuenta:
    equipo → lo que hizo ese equipo + lo que concedió el rival; total → totales de los partidos de ambos."""
    m = res["match"]
    L, V = m["local"], m["visitante"]

    def val(x, lado, k):
        if k == "tarjetas":
            return x[lado]["amarillas"] + x[lado]["rojas"]
        return x[lado].get(k)

    forma = res.get("forma") or {}
    if ambito == "total":
        return [val(x, "favor", s) + val(x, "contra", s) for t in (L, V) for x in forma.get(t, [])]
    t, r = (L, V) if ambito == "local" else (V, L)
    return [val(x, "favor", s) for x in forma.get(t, [])] + [val(x, "contra", s) for x in forma.get(r, [])]


def _candidato_equipo(out, base, p_over, media_mod, valores, c_over, c_under):
    p_casa = MK.sin_margen([c_over, c_under]) if c_over and c_under else None
    if not p_casa:
        return
    linea = base["linea"]
    valores = [v for v in valores if v is not None]
    n = len(valores)
    prom = sum(valores) / n if n else None
    for lado, p_mod, cuota, pc in (("over", p_over, c_over, p_casa[0]), ("under", 1 - p_over, c_under, p_casa[1])):
        hits = sum((v > linea) if lado == "over" else (v < linea) for v in valores)
        p_hist = (hits + HIST_K * pc) / (n + HIST_K) if n else None
        evid = (p_mod + p_hist) / 2 if p_hist is not None else p_mod
        p = MK.mezclar(evid, pc, EVID_W)
        e = MK.ev(p, cuota)
        a_favor = p_mod >= 0.5 and (p_hist is None or p_hist >= 0.5)
        lejos = prom is not None and ((lado == "over" and prom >= linea * (1 + ERR_DIST)) or (lado == "under" and prom <= linea * (1 - ERR_DIST)))
        error = bool(n >= 6 and hits / n >= ERR_MIN_HIST and pc <= ERR_MAX_CASA and lejos and p_mod >= 0.5)
        if error or (a_favor and p >= P.MIN_P and e >= P.VALUE_EV):
            out.append({**base, "lado": lado, "cuota": cuota, "p_modelo": round(p_mod, 3), "p_casa": round(pc, 3),
                        "p_hist": round(p_hist, 3) if p_hist is not None else None, "aciertos": hits, "n_hist": n,
                        "prom_hist": round(prom, 2) if prom is not None else None, "media_modelo": round(media_mod, 2),
                        "p": round(p, 3), "ev": round(e, 3), "error_cuota": error, "puntaje": round(e * p + (0.05 if error else 0), 4)})


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
    # ---- equipo y partido: modelo + cumplimiento histórico + cuota (picks de valor y errores de cuota)
    eq_out = []
    for c in (partido.get("cuotas") or {}).get("equipo") or []:
        s = c.get("stat")
        if s not in STATS_PICK_EQUIPO:
            continue
        sim_stat = lambda i: (sim["team"][i]["amarillas"] + sim["team"][i]["rojas"]) if s == "tarjetas" else sim["team"][i][s]
        tl, tv = sim_stat(0), sim_stat(1)
        ambito = c.get("ambito", "total")
        x = {"total": tl + tv, "local": tl, "visitante": tv}.get(ambito)
        if x is None:
            continue
        quien = {"total": "partido", "local": L, "visitante": V}[ambito]
        valores = _historial_linea(res, s, ambito)
        _candidato_equipo(eq_out, {"tipo": "equipo", "jugador": quien, "equipo": quien, "stat": s, "linea": c["linea"],
                                   "casa": c.get("casa"), "suplente_oro": False},
                          float((x > c["linea"]).mean()), float(x.mean()), valores, c.get("over"), c.get("under"))
    # un solo lado/línea por mercado: el de mayor puntaje (evita recomendar 4 líneas del mismo mercado)
    mejor = {}
    for x in eq_out:
        k = (x["equipo"], x["stat"], x["lado"])
        if k not in mejor or x["puntaje"] > mejor[k]["puntaje"]:
            mejor[k] = x
    out.extend(mejor.values())
    out.sort(key=lambda x: -(x.get("puntaje") or x["ev"] * x["p"]))
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
            "utc": iso(inicio_utc(m)), "picks_salen": res.get("picks_salen"),
            "jornada": m.get("jornada"), "local": L, "visitante": V, "estadio": m.get("estadio"), "derbi": res["derbi"],
            "arbitro": res["arbitro"].get("nombre"), "1x2": pa["1x2"], "goles": pa["total_goles"]["dist"]["media"],
            "over25": next(p for l, p in pa["total_goles"]["over"] if l == 2.5), "ambos": pa["ambos_marcan"],
            "corners": pa["totales"]["corners"]["dist"]["media"], "amarillas": pa["totales"]["amarillas"]["dist"]["media"],
            "marcador": pa["marcadores"][0], "n_picks": len(res["picks"]), "ejemplo": res["ejemplo"],
            "n_errores": sum(1 for x in res["picks"] if x.get("error_cuota")),
            "cuotas_capturadas": (res.get("cuotas_casa") or {}).get("capturado"),
            "alineacion": {t: res["alineacion"][t]["estado"] for t in (L, V)},
            "bajas": {t: len(res["bajas"][t]["lista"]) for t in (L, V)}}


HORA_PICKS = 19          # 7:00 pm Bogotá de la víspera del primer partido de la jornada
BOGOTA = timezone(timedelta(hours=-5))


def inicio_utc(m):
    """Hora de inicio del partido (UTC): `utc` de FotMob, o fecha + hora de Bogotá."""
    if m.get("utc"):
        return datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
    h = m.get("hora_bogota") or "12:00"
    return datetime.fromisoformat(f'{m["fecha"]}T{h}').replace(tzinfo=BOGOTA).astimezone(timezone.utc)


def picks_salen(partidos):
    """{jornada: hora UTC desde la que se publican sus picks} = HORA_PICKS de la víspera del primer partido."""
    primero = {}
    for p in partidos:
        j = p["match"].get("jornada")
        if j is None:
            continue
        t = inicio_utc(p["match"])
        primero[j] = min(primero.get(j, t), t)
    out = {}
    for j, t in primero.items():
        dia = t.astimezone(BOGOTA).date() - timedelta(days=1)
        out[j] = datetime(dia.year, dia.month, dia.day, HORA_PICKS, tzinfo=BOGOTA).astimezone(timezone.utc)
    return out


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("liga", choices=list(LIGAS))
    ap.add_argument("fecha", nargs="?")
    ap.add_argument("--sims", type=int, default=P.SIMS)
    ap.add_argument("--solo-futuros", action="store_true",
                    help="solo partidos que no han empezado (lo publicado de los empezados queda congelado)")
    ap.add_argument("--picks-ya", action="store_true",
                    help="publica los picks aunque todavía no sea la noche anterior al primer partido de la jornada")
    a = ap.parse_args()
    cfg = LIGAS[a.liga]
    hist = cargar(os.path.join(RAIZ, "futbol", a.liga, "historico", "*.json"))
    partidos = cargar(os.path.join(RAIZ, "futbol", a.liga, "partidos", "*.json"))
    salen = picks_salen(partidos)   # con todos los partidos de la jornada, antes de filtrar
    if a.fecha:
        partidos = [p for p in partidos if p["match"]["fecha"] == a.fecha]
    if a.solo_futuros:
        ahora = datetime.now(timezone.utc)
        partidos = [p for p in partidos if not p["match"].get("utc")
                    or datetime.fromisoformat(p["match"]["utc"].replace("Z", "+00:00")) > ahora]
        if not partidos:
            print("No hay partidos por empezar: no se re-simula nada.")
            return
    outdir = os.path.join(RAIZ, "docs", cfg["web"], "data")
    os.makedirs(outdir, exist_ok=True)
    idx_path = os.path.join(outdir, "index.json")
    idx = {"partidos": []}
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            idx = json.load(fh)
    viejos = {p["id"]: p for p in idx.get("partidos", [])}
    from futbol.datos import betano
    for p in partidos:
        pid = p.get("id") or f'{p["match"]["fecha"]}-{p["match"]["local"]}-{p["match"]["visitante"]}'
        f_cuotas = os.path.join(RAIZ, "futbol", a.liga, "cuotas", pid + ".json")
        extracto = None
        if os.path.exists(f_cuotas):
            with open(f_cuotas, encoding="utf-8") as fh:
                extracto = json.load(fh)
            cu = dict(p.get("cuotas") or {})
            cu["equipo"] = list(cu.get("equipo") or []) + betano.cuotas_equipo(p, extracto)
            p = {**p, "cuotas": cu}
        res = predecir(a.liga, p, hist, a.sims)
        sale = salen.get(p["match"].get("jornada"))
        if sale:
            res["picks_salen"] = iso(sale)
            if not a.picks_ya and datetime.now(timezone.utc) < sale:
                res["picks"] = []   # todavía no: se publican la víspera del primer partido de la jornada
        cons = _consenso(a.liga, res["id"])
        if cons:
            res["consenso"] = cons
        if extracto:
            mk = extracto.get("mercados") or {}
            res["cuotas_casa"] = {"casa": extracto.get("casa"), "capturado": extracto.get("capturado"),
                                  "1x2": mk.get("Resultado del partido"), "ambos": mk.get("Ambos equipos anotan")}
        with open(os.path.join(outdir, res["id"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
        viejos[res["id"]] = resumen(res)
        print(f'{res["id"]}: 1X2 {res["partido"]["1x2"]}  goles {res["partido"]["total_goles"]["dist"]["media"]}  picks {len(res["picks"])}')
    lista = sorted(viejos.values(), key=lambda x: (x["fecha"], x.get("hora_local") or "", x["id"]))
    idx = {"liga": cfg["nombre"], "temporada": cfg["temporada"], "version": P.MODEL_VERSION,
           "actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "ejemplo": any(x.get("ejemplo") for x in lista), "hora_picks_bogota": HORA_PICKS,
           "picks_salen": {str(j): iso(t) for j, t in sorted(salen.items())}, "partidos": lista}
    with open(idx_path, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=1)
    # Resultados reales de los partidos ya jugados (para liquidar "Mis picks" en la web): stats por equipo.
    jugados = {}
    for x in hist:
        if x.get("temporada") != cfg["temporada"] or not x.get("equipos"):
            continue
        jugados[x["id"]] = {"local": x["local"], "visitante": x["visitante"],
                            "equipos": {t: {k: v for k, v in e.items() if k in STATS_RESULTADO} for t, e in x["equipos"].items()}}
    with open(os.path.join(outdir, "resultados.json"), "w", encoding="utf-8") as fh:
        json.dump({"actualizado": idx["actualizado"], "partidos": jugados}, fh, ensure_ascii=False, separators=(",", ":"))


def _consenso(liga, pid):
    """Última foto del consenso de casas (futbol/<liga>/consenso/*.json, de The Odds API) para ese partido."""
    for f in sorted(glob.glob(os.path.join(RAIZ, "futbol", liga, "consenso", "*.json")), reverse=True):
        with open(f, encoding="utf-8") as fh:
            fotos = json.load(fh)
        for foto in reversed(fotos):
            p = (foto.get("partidos") or {}).get(pid)
            if p:
                out = {"hora": foto["hora"]}
                for k, v in p.items():
                    if k == "1x2" or k == "goles 2.5":
                        out[k] = {x: v[x] for x in ("n", "mejor", "consenso", "pinnacle")}
                return out
    return None


STATS_RESULTADO = ("goles", "corners", "amarillas", "rojas", "faltas", "remates", "remates_puerta", "offsides")


if __name__ == "__main__":
    main()
