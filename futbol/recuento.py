"""Recuento de los picks publicados de una liga contra los resultados reales.

Uso:  python -m futbol.recuento serie_a

Lee lo publicado (docs/<web>/data/<partido>.json: picks, 1X2 del modelo y consenso de casas) y el histórico de
FotMob (futbol/<liga>/historico/*.json). Cada pick de un partido ya jugado se liquida a 1 unidad y se guarda en
futbol/<liga>/recuento/picks.json, que se va acumulando (un pick liquidado no se vuelve a tocar aunque el JSON
del partido cambie o desaparezca). Escribe docs/<web>/data/recuento.json para la sección Rendimiento de la web:
resumen, por estadística, por casa, por jornada, picks y calibración del 1X2 (modelo vs mercado).
"""
import glob
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = {"serie_a": "serie-a"}
STAT_JUG = {"faltas": "faltas_cometidas"}   # nombre del stat del pick -> campo del histórico de jugadores


def _cargar(p, defecto):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return defecto


def _norm(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def clave(pid, k):
    return f'{pid}|{k["tipo"]}|{k["jugador"]}|{k["stat"]}|{k["linea"]}|{k["lado"]}'


def real_de(k, h):
    """Valor real de la estadística del pick en el partido h (histórico) o None si no se puede saber."""
    if k["tipo"] == "equipo":
        def v(t):
            e = h["equipos"].get(t) or {}
            if k["stat"] == "tarjetas":
                return None if "amarillas" not in e else e.get("amarillas", 0) + e.get("rojas", 0)
            return e.get(k["stat"])
        if k["jugador"] == "partido":
            a, b = v(h["local"]), v(h["visitante"])
            return None if a is None or b is None else a + b
        return v(k["jugador"])
    js = (h.get("jugadores") or {}).get(k.get("equipo"), [])
    j = next((x for x in js if _norm(x["nombre"]) == _norm(k["jugador"])), None)
    if not j or not j.get("jugo"):
        return "no jugó"
    campo = STAT_JUG.get(k["stat"], k["stat"])
    if k["stat"] == "tarjetas":
        return j.get("amarillas", 0) + j.get("rojas", 0)
    return j.get(campo)


def liquidar(k, h):
    real = real_de(k, h)
    if real == "no jugó":
        return {"estado": "nulo", "real": None, "u": 0.0}
    if real is None:
        return None
    gana = real > k["linea"] if k["lado"] == "over" else real < k["linea"]
    return {"estado": "ganado" if gana else "perdido", "real": real, "u": round(k["cuota"] - 1, 3) if gana else -1.0}


def _resumen(xs):
    hechos = [x for x in xs if x["estado"] in ("ganado", "perdido")]
    g = sum(x["estado"] == "ganado" for x in hechos)
    u = sum(x["u"] for x in hechos)
    return {"n": len(hechos), "ganados": g, "perdidos": len(hechos) - g, "acierto": round(g / len(hechos), 4) if hechos else None,
            "unidades": round(u, 2), "roi": round(u / len(hechos), 4) if hechos else None,
            "cuota_media": round(sum(x["cuota"] for x in hechos) / len(hechos), 2) if hechos else None,
            "p_media": round(sum(x.get("p") or 0 for x in hechos) / len(hechos), 4) if hechos else None}


def _logloss(p, i):
    return -math.log(max(1e-6, p[i]))


def main(liga):
    web = WEB[liga]
    dd = os.path.join(RAIZ, "docs", web, "data")
    hist = {}
    for f in glob.glob(os.path.join(RAIZ, "futbol", liga, "historico", "*.json")):
        for h in _cargar(f, []):
            if h.get("equipos"):
                hist[h["id"]] = h
    f_acum = os.path.join(RAIZ, "futbol", liga, "recuento", "picks.json")
    acum = _cargar(f_acum, {"picks": {}, "partidos": {}})

    for f in sorted(glob.glob(os.path.join(dd, "20*.json"))):
        d = _cargar(f, None)
        if not d or d.get("ejemplo"):
            continue
        pid = d["id"]
        h = hist.get(pid)
        if not h:
            continue
        m = d["match"]
        for k in d.get("picks") or []:
            ck = clave(pid, k)
            if ck in acum["picks"]:
                continue
            r = liquidar(k, h)
            if r is None:
                continue
            acum["picks"][ck] = {"id": pid, "fecha": m["fecha"], "local": m["local"], "visitante": m["visitante"],
                                 **{c: k.get(c) for c in ("tipo", "jugador", "equipo", "stat", "linea", "lado", "cuota", "casa",
                                                          "p", "p_modelo", "p_casa", "ev", "error_cuota", "suplente_oro")},
                                 **r}
        if pid not in acum["partidos"]:
            gl, gv = h["equipos"][h["local"]].get("goles"), h["equipos"][h["visitante"]].get("goles")
            if gl is None or gv is None:
                continue
            i = 0 if gl > gv else 1 if gl == gv else 2
            cons = (d.get("consenso") or {}).get("1x2") or {}
            acum["partidos"][pid] = {"fecha": m["fecha"], "local": m["local"], "visitante": m["visitante"],
                                     "marcador": f"{gl}-{gv}", "resultado": i, "modelo": d["partido"]["1x2"],
                                     "mercado": cons.get("consenso"), "pinnacle": cons.get("pinnacle"),
                                     "over25_modelo": d["partido"]["total_goles"]["over"] and next(
                                         (p for l, p in d["partido"]["total_goles"]["over"] if l == 2.5), None),
                                     "goles": gl + gv}

    os.makedirs(os.path.dirname(f_acum), exist_ok=True)
    with open(f_acum, "w", encoding="utf-8") as fh:
        json.dump(acum, fh, ensure_ascii=False, indent=1)

    picks = sorted(acum["picks"].values(), key=lambda x: (x["fecha"], x["id"]), reverse=True)
    por = lambda campo: {k: _resumen(v) for k, v in sorted(_grupo(picks, campo).items())}
    partidos = sorted(acum["partidos"].values(), key=lambda x: x["fecha"])
    cal = {"n": len(partidos)}
    if partidos:
        cal["acierto_favorito_modelo"] = round(sum(max(range(3), key=lambda j: p["modelo"][j]) == p["resultado"] for p in partidos) / len(partidos), 4)
        cal["logloss_modelo"] = round(sum(_logloss(p["modelo"], p["resultado"]) for p in partidos) / len(partidos), 4)
        conm = [p for p in partidos if p.get("mercado")]
        if conm:
            cal["n_mercado"] = len(conm)
            cal["logloss_modelo_mismos"] = round(sum(_logloss(p["modelo"], p["resultado"]) for p in conm) / len(conm), 4)
            cal["logloss_mercado"] = round(sum(_logloss(p["mercado"], p["resultado"]) for p in conm) / len(conm), 4)
            cal["acierto_favorito_mercado"] = round(sum(max(range(3), key=lambda j: p["mercado"][j]) == p["resultado"] for p in conm) / len(conm), 4)
    out = {"actualizado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "resumen": _resumen(picks),
           "errores_cuota": _resumen([x for x in picks if x.get("error_cuota")]),
           "por_stat": por("stat"), "por_casa": por("casa"), "por_fecha": por("fecha"),
           "calibracion_1x2": cal, "partidos": list(reversed(partidos)), "picks": picks}
    with open(os.path.join(dd, "recuento.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    r = out["resumen"]
    print(f"Recuento {liga}: {r['n']} picks liquidados, {r['ganados']} ganados, {r['unidades']:+} u (ROI {r['roi']}); "
          f"{cal['n']} partidos en la calibración del 1X2")


def _grupo(xs, campo):
    g = defaultdict(list)
    for x in xs:
        g[x.get(campo) or "–"].append(x)
    return g


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "serie_a")
