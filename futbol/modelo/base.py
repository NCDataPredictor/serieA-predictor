"""BD de contexto de fútbol a partir de los partidos históricos normalizados (el db/ de la NBA).

Entrada: una lista de partidos en el formato normalizado (ver futbol/datos/FORMATO.md), que escriben los
descargadores de futbol/datos/. Salida: un dict con

  liga      medias por partido y equipo, perfil por tramos de 15', reparto por zonas y por tipo de jugada
  equipos   por equipo: a favor / en contra por estadística (temporada, anterior, últimos 10, local/visitante),
            tramos a favor y en contra, zonas de ataque y zonas por donde le atacan, tipos de jugada,
            últimos 10 partidos, H2H por rival
  jugadores por equipo y jugador: tasas por 90 (temporada, anterior, últimos 10 del equipo), titularidades,
            minutos de salida y de entrada, quién lo reemplaza, efecto con/sin de cada jugador en el equipo
  arbitros  por árbitro: partidos con tarjetas y faltas (para su media y los últimos 5)

Todo es determinista y se puede rehacer para cualquier fecha (`hasta=`): así el backtest usa solo lo que se
sabía antes de cada partido.
"""
from collections import defaultdict
from datetime import date

from . import params as P

ZONAS = ["izq", "centro", "der"]
SITUACIONES = ["jugada", "contragolpe", "balon_parado", "penalti"]
ESPEJO = {"izq": "der", "centro": "centro", "der": "izq"}   # la izquierda del atacante es la derecha del defensor


def _d(s):
    return date.fromisoformat(s[:10])


def tramo_de(minuto):
    """Índice de tramo (0..5) de un minuto; el añadido (45+2, 90+4) cae en el último tramo de cada tiempo."""
    m = int(minuto)
    if m <= 0:
        m = 1
    for i, (a, b) in enumerate(P.TRAMOS):
        if a <= m <= b:
            return i
    return 2 if m < 46 else 5


def tipos_evento(ev):
    """Estadísticas a las que cuenta un evento: un remate a puerta cuenta como remate y como remate a puerta."""
    t = ev["tipo"]
    if t == "remates":
        return ["remates", "remates_puerta"] if ev.get("a_puerta") else ["remates"]
    return [t]


REPARTO_TIEMPO = {"1": [(0, 0.30), (1, 0.32), (2, 0.38)], "2": [(3, 0.31), (4, 0.32), (5, 0.37)]}


def eventos_tramo(p, eq):
    """(estadística, tramo, cantidad) de `eq` en el partido: de los eventos con minuto y, para las estadísticas que no
    traen eventos (córners, faltas, fueras de lugar en FotMob), de los totales por tiempo repartidos en sus 3 tramos."""
    out = []
    con_eventos = set()
    for ev in p.get("eventos", []):
        if ev["equipo"] != eq:
            continue
        for t in tipos_evento(ev):
            con_eventos.add(t)
            out.append((t, tramo_de(ev["min"]), 1.0))
    for tiempo, st in ((p.get("por_tiempo") or {}).get(eq) or {}).items():
        for s, v in st.items():
            if s in con_eventos or not v:
                continue
            for k, w in REPARTO_TIEMPO.get(tiempo, []):
                out.append((s, k, v * w))
    return out


def _vacio_stats():
    return {s: 0.0 for s in P.STATS_EQUIPO}


def _rival(p, eq):
    return p["visitante"] if eq == p["local"] else p["local"]


def construir(partidos, temporada, hasta=None, temporada_ant=None):
    """Construye la BD con los partidos jugados ANTES de `hasta` (ISO). `temporada` = la que se predice."""
    hasta_d = _d(hasta) if hasta else None
    ps = [p for p in partidos if hasta_d is None or _d(p["fecha"]) < hasta_d]
    ps.sort(key=lambda p: p["fecha"])
    liga = _liga(ps, temporada)
    equipos = _equipos(ps, temporada, temporada_ant, liga)
    jugadores = _jugadores(ps, temporada, temporada_ant)
    arbitros = _arbitros(ps, temporada, temporada_ant)
    _con_sin(ps, temporada, jugadores)
    return {"temporada": temporada, "hasta": hasta, "n_partidos": len(ps), "liga": liga, "equipos": equipos,
            "jugadores": jugadores, "arbitros": arbitros, "partidos": ps}


# ------------------------------------------------------------------------------------------------- liga
def _liga(ps, temporada):
    """Medias por equipo y partido, perfil de tramos y repartos de la liga (temporada actual + anterior)."""
    tot = _vacio_stats()
    n = 0
    tramos = {s: [0.0] * 6 for s in P.STATS_EQUIPO}
    zonas = {z: 0.0 for z in ZONAS}
    sit = {s: 0.0 for s in SITUACIONES}
    local_g = visit_g = 0.0
    nl = 0
    # medias por temporada por separado: el nivel de la liga cambia de un año a otro (2026-27 trae ~20% más remates
    # y ~14% menos faltas que 2025-26), así que la media es la de la temporada en curso encogida hacia la anterior
    tot_t = {k: _vacio_stats() for k in ("act", "ant")}
    n_t = {"act": 0, "ant": 0}
    for p in ps:
        w = 1.0 if p["temporada"] == temporada else 0.6
        k_t = "act" if p["temporada"] == temporada else "ant"
        for eq in (p["local"], p["visitante"]):
            st = p["equipos"][eq]
            for s in P.STATS_EQUIPO:
                tot[s] += w * st.get(s, 0)
                tot_t[k_t][s] += st.get(s, 0)
            n += w
            n_t[k_t] += 1
        local_g += w * p["equipos"][p["local"]]["goles"]
        visit_g += w * p["equipos"][p["visitante"]]["goles"]
        nl += w
        for eq in (p["local"], p["visitante"]):
            for t, k, c in eventos_tramo(p, eq):
                if t in tramos:
                    tramos[t][k] += w * c
        for ev in p.get("eventos", []):
            s = ev["tipo"]
            if s == "remates":
                if ev.get("zona") in zonas:
                    zonas[ev["zona"]] += w
                if ev.get("situacion") in sit:
                    sit[ev["situacion"]] += w
    medias_mix = {s: (tot[s] / n if n else 0.0) for s in P.STATS_EQUIPO}
    m_ant = {s: (tot_t["ant"][s] / n_t["ant"] if n_t["ant"] else medias_mix[s]) for s in P.STATS_EQUIPO}
    m_act = {s: (tot_t["act"][s] / n_t["act"] if n_t["act"] else m_ant[s]) for s in P.STATS_EQUIPO}
    w_act = n_t["act"] / (n_t["act"] + P.NIVEL_LIGA_K)
    medias = {s: w_act * m_act[s] + (1 - w_act) * m_ant[s] for s in P.STATS_EQUIPO}
    # factor para llevar lo de la temporada anterior (por equipo) al nivel de la actual
    nivel = {s: (medias[s] / m_ant[s] if m_ant[s] > 0 else 1.0) for s in P.STATS_EQUIPO}
    perfil = {}
    for s, v in tramos.items():
        t = sum(v)
        # Sin eventos con minuto para esta estadística: reparto uniforme (cada tramo 1/6).
        perfil[s] = [x / t for x in v] if t > 0 else [1 / 6] * 6
    zt = sum(zonas.values()) or 1
    stt = sum(sit.values()) or 1
    return {"medias": medias, "nivel_temporada": nivel, "perfil_tramos": perfil,
            "zonas": {z: zonas[z] / zt if sum(zonas.values()) else 1 / 3 for z in ZONAS},
            "situaciones": {s: sit[s] / stt if sum(sit.values()) else 0.25 for s in SITUACIONES},
            "localia_goles": (local_g / visit_g) if visit_g else P.LOCALIA_GOLES, "n_partidos_eq": n}


# ---------------------------------------------------------------------------------------------- equipos
def _equipos(ps, temporada, temporada_ant, liga):
    E = defaultdict(lambda: {
        "pj": 0, "pj_ant": 0,
        "favor": _vacio_stats(), "contra": _vacio_stats(),
        "favor_ant": _vacio_stats(), "contra_ant": _vacio_stats(),
        "local": {"pj": 0, "favor": _vacio_stats(), "contra": _vacio_stats()},
        "visit": {"pj": 0, "favor": _vacio_stats(), "contra": _vacio_stats()},
        "tramos_favor": {s: [0.0] * 6 for s in P.STATS_EQUIPO},
        "tramos_contra": {s: [0.0] * 6 for s in P.STATS_EQUIPO},
        "zonas_ataque": {z: 0.0 for z in ZONAS}, "zonas_concede": {z: 0.0 for z in ZONAS},
        "sit_ataque": {s: 0.0 for s in SITUACIONES}, "sit_concede": {s: 0.0 for s in SITUACIONES},
        "posesion": [], "partidos": [], "pases_ok": 0.0, "pases_tot": 0.0,
    })
    for p in ps:
        actual = p["temporada"] == temporada
        for eq in (p["local"], p["visitante"]):
            r = _rival(p, eq)
            e = E[eq]
            fav, con = p["equipos"][eq], p["equipos"][r]
            if actual:
                e["pj"] += 1
                for s in P.STATS_EQUIPO:
                    e["favor"][s] += fav.get(s, 0)
                    e["contra"][s] += con.get(s, 0)
                lado = e["local"] if eq == p["local"] else e["visit"]
                lado["pj"] += 1
                for s in P.STATS_EQUIPO:
                    lado["favor"][s] += fav.get(s, 0)
                    lado["contra"][s] += con.get(s, 0)
                if fav.get("posesion") is not None:
                    e["posesion"].append(fav["posesion"])
            elif p["temporada"] == temporada_ant:
                e["pj_ant"] += 1
                for s in P.STATS_EQUIPO:
                    e["favor_ant"][s] += fav.get(s, 0)
                    e["contra_ant"][s] += con.get(s, 0)
            # Precisión de pase del equipo: FotMob da pases ACERTADOS por jugador y pases TOTALES por equipo.
            pj_ok = sum(j.get("pases", 0) or 0 for j in p.get("jugadores", {}).get(eq, []))
            if pj_ok > 0 and fav.get("pases"):
                e["pases_ok"] += pj_ok
                e["pases_tot"] += fav["pases"]
            # Tramos, zonas y tipos de jugada: temporada actual y anterior (la anterior pesa 0,6).
            w = 1.0 if actual else 0.6
            for t, k, c in eventos_tramo(p, eq):
                if t in e["tramos_favor"]:
                    e["tramos_favor"][t][k] += w * c
            for t, k, c in eventos_tramo(p, r):
                if t in e["tramos_contra"]:
                    e["tramos_contra"][t][k] += w * c
            # zonas y tipo de jugada de los remates (los que concede se guardan desde el lado del DEFENSOR)
            for ev in p.get("eventos", []):
                if ev["tipo"] != "remates":
                    continue
                z, si = ev.get("zona"), ev.get("situacion")
                if ev["equipo"] == eq:
                    if z in ZONAS:
                        e["zonas_ataque"][z] += w
                    if si in SITUACIONES:
                        e["sit_ataque"][si] += w
                else:
                    if z in ZONAS:
                        e["zonas_concede"][ESPEJO[z]] += w
                    if si in SITUACIONES:
                        e["sit_concede"][si] += w
            e["partidos"].append(_resumen_partido(p, eq))
    out = {}
    for eq, e in E.items():
        e["ultimos10"] = [x for x in e["partidos"] if x["temporada"] == temporada][-10:]
        # Si aún no hay 10 en la temporada, se completan con el final de la anterior (como en NBA).
        if len(e["ultimos10"]) < 10:
            prev = [x for x in e["partidos"] if x["temporada"] != temporada]
            e["ultimos10"] = (prev[-(10 - len(e["ultimos10"])):] if prev else []) + e["ultimos10"]
        out[eq] = e
    return out


def _resumen_partido(p, eq):
    r = _rival(p, eq)
    fav, con = p["equipos"][eq], p["equipos"][r]
    gf, gc = fav["goles"], con["goles"]
    return {"id": p["id"], "fecha": p["fecha"], "temporada": p["temporada"], "competicion": p.get("competicion", "liga"),
            "rival": r, "local": eq == p["local"], "gf": gf, "gc": gc,
            "res": "G" if gf > gc else ("E" if gf == gc else "P"),
            "favor": {s: fav.get(s, 0) for s in P.STATS_EQUIPO},
            "contra": {s: con.get(s, 0) for s in P.STATS_EQUIPO},
            "xg": fav.get("xg"), "xga": con.get("xg"), "arbitro": p.get("arbitro"),
            "derbi": bool(p.get("derbi"))}


# -------------------------------------------------------------------------------------------- jugadores
def _jugadores(ps, temporada, temporada_ant):
    J = defaultdict(dict)
    # Los últimos 10 partidos de cada equipo (de cualquier temporada) para la forma reciente del jugador.
    por_eq = defaultdict(list)
    for p in ps:
        for eq in (p["local"], p["visitante"]):
            por_eq[eq].append(p["id"])
    ult10 = {eq: set(ids[-10:]) for eq, ids in por_eq.items()}
    for p in ps:
        actual = p["temporada"] == temporada
        for eq in (p["local"], p["visitante"]):
            lst = p.get("jugadores", {}).get(eq, [])
            # quién entra por quién (para el suplente de oro y para saber quién hereda el puesto)
            reemplazo = {c["sale"]: c["entra"] for c in p.get("cambios", {}).get(eq, [])}
            for j in lst:
                jid = j["id"]
                rec = J[eq].get(jid)
                if rec is None:
                    rec = J[eq][jid] = {"id": jid, "nombre": j["nombre"], "pos": j.get("pos", "MC"), "lado": j.get("lado", "centro"),
                                        "dorsal": j.get("dorsal"),
                                        "act": _acum(), "ant": _acum(), "u10": _acum(),
                                        "titular_u10": 0, "convocado_u10": 0, "min_salida": [], "min_entrada": [],
                                        "reemplazado_por": defaultdict(int), "reemplaza_a": defaultdict(int),
                                        "partidos": []}
                rec["nombre"] = j["nombre"]
                rec["pos"] = j.get("pos", rec["pos"])
                rec["lado"] = j.get("lado", rec["lado"])
                mins = max(0, j.get("min_sale", 90) - j.get("min_entra", 0)) if j.get("jugo", True) else 0
                bucket = rec["act"] if actual else (rec["ant"] if p["temporada"] == temporada_ant else None)
                if bucket is not None and mins > 0:
                    _sumar(bucket, j, mins)
                if p["id"] in ult10.get(eq, ()):
                    rec["convocado_u10"] += 1
                    if j.get("titular"):
                        rec["titular_u10"] += 1
                    if mins > 0:
                        _sumar(rec["u10"], j, mins)
                if j.get("titular") and mins > 0:
                    rec["min_salida"].append(min(90, j.get("min_sale", 90)))
                if not j.get("titular") and mins > 0:
                    rec["min_entrada"].append(j.get("min_entra", 70))
                if jid in reemplazo:
                    rec["reemplazado_por"][reemplazo[jid]] += 1
                for sale, entra in reemplazo.items():
                    if entra == jid:
                        rec["reemplaza_a"][sale] += 1
                rec["partidos"].append({"id": p["id"], "fecha": p["fecha"], "titular": bool(j.get("titular")), "min": mins,
                                        "rival": _rival(p, eq),
                                        **{s: j.get(s, 0) for s in P.STATS_JUGADOR}})
    # Banda de cada jugador según dónde remata (más fiable que la posición del dibujo táctico): con 6+ remates
    # con zona, si más del 50% caen por un lado, ese es su lado.
    zonas_j = defaultdict(lambda: defaultdict(int))
    for p in ps:
        for ev in p.get("eventos", []):
            if ev["tipo"] == "remates" and ev.get("jugador") and ev.get("zona"):
                zonas_j[ev["jugador"]][ev["zona"]] += 1
    for eq in J:
        for jid, rec in J[eq].items():
            z = zonas_j.get(jid)
            if z and sum(z.values()) >= 6:
                top = max(z, key=z.get)
                if top != "centro" and z[top] / sum(z.values()) > 0.5:
                    rec["lado"] = top
    # defaultdict -> dict (JSON)
    for eq in J:
        for rec in J[eq].values():
            rec["reemplazado_por"] = dict(rec["reemplazado_por"])
            rec["reemplaza_a"] = dict(rec["reemplaza_a"])
    return {eq: dict(v) for eq, v in J.items()}


def _acum():
    return {"min": 0, "pj": 0, **{s: 0.0 for s in P.STATS_JUGADOR}, "amarillas": 0}


def _sumar(b, j, mins):
    b["min"] += mins
    b["pj"] += 1
    for s in P.STATS_JUGADOR:
        b[s] += j.get(s, 0)
    b["amarillas"] += j.get("amarillas", 0)


# --------------------------------------------------------------------------------------------- árbitros
def _arbitros(ps, temporada, temporada_ant):
    A = defaultdict(list)
    for p in ps:
        if not p.get("arbitro"):
            continue
        l, v = p["equipos"][p["local"]], p["equipos"][p["visitante"]]
        A[p["arbitro"]].append({"fecha": p["fecha"], "temporada": p["temporada"], "partido": f'{p["local"]}-{p["visitante"]}',
                                "amarillas": l.get("amarillas", 0) + v.get("amarillas", 0),
                                "rojas": l.get("rojas", 0) + v.get("rojas", 0),
                                "faltas": l.get("faltas", 0) + v.get("faltas", 0),
                                "penaltis": p.get("penaltis", 0)})
    return dict(A)


# ------------------------------------------------------------------------------------ efecto con / sin
def _con_sin(ps, temporada, jugadores):
    """Para cada jugador habitual: cómo rinde el equipo (y cada compañero) en los partidos en que NO juega.

    Es el análogo del "sin X" de without.py en NBA, pero medido en datos: si el 9 titular falta, ¿cuántos
    remates hace el equipo y cuántos se lleva cada compañero? Con pocas muestras manda el reparto automático
    (los demás heredan su parte en proporción a su volumen), ver bajas.py.
    """
    act = [p for p in ps if p["temporada"] == temporada]
    for eq, js in jugadores.items():
        partidos_eq = [p for p in act if eq in (p["local"], p["visitante"])]
        if not partidos_eq:
            continue
        habituales = [jid for jid, r in js.items() if r["act"]["pj"] >= max(3, len(partidos_eq) // 3)]
        for jid in habituales:
            con, sin = [], []
            for p in partidos_eq:
                jugo = any(j["id"] == jid and j.get("min_sale", 90) - j.get("min_entra", 0) > 0 and j.get("jugo", True)
                           for j in p.get("jugadores", {}).get(eq, []))
                (con if jugo else sin).append(p)
            if not sin:
                continue
            res = {"n_con": len(con), "n_sin": len(sin), "equipo": {}, "companeros": {}}
            for s in ("remates", "remates_puerta", "goles", "pases", "corners"):
                mc = sum(p["equipos"][eq].get(s, 0) for p in con) / max(1, len(con))
                ms = sum(p["equipos"][eq].get(s, 0) for p in sin) / len(sin)
                res["equipo"][s] = {"con": round(mc, 2), "sin": round(ms, 2)}
            # Tasa por 90 de cada compañero con y sin él (solo compañeros con minutos en ambos grupos).
            for cid, c in js.items():
                if cid == jid:
                    continue
                m_con = _tasas_en(c, {p["id"] for p in con})
                m_sin = _tasas_en(c, {p["id"] for p in sin})
                if m_con["min"] >= 180 and m_sin["min"] >= 90:
                    res["companeros"][cid] = {"min_sin": m_sin["min"],
                                              **{s: {"con": m_con[s], "sin": m_sin[s]} for s in P.STATS_JUGADOR},
                                              "titular_con": m_con["tit"], "titular_sin": m_sin["tit"]}
            js[jid]["con_sin"] = res


def _tasas_en(rec, ids):
    mins = 0
    tit = 0
    n = 0
    tot = {s: 0.0 for s in P.STATS_JUGADOR}
    for x in rec["partidos"]:
        if x["id"] in ids:
            n += 1
            mins += x["min"]
            tit += 1 if x["titular"] else 0
            for s in P.STATS_JUGADOR:
                tot[s] += x[s]
    out = {s: round(tot[s] * 90 / mins, 3) if mins else 0.0 for s in P.STATS_JUGADOR}
    out["min"] = mins
    out["tit"] = round(tit / n, 2) if n else 0.0
    return out
