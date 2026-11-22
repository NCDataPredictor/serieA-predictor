"""Participación y tasas de los jugadores de un partido, con las bajas aplicadas.

La lección 8 de NBA: lo que más explica el error de un prop es la participación (en NBA, los minutos; aquí,
¿es titular? ¿a qué minuto sale? ¿quién entra?). Por eso cada jugador lleva:

  p_titular       oficial (1/0) > probable de la prensa > titularidades en los últimos 10
  salida          minuto de salida de sus titularidades (media, DE) y % de partidos completos
  entrada         prob. de entrar desde el banco y minuto medio de entrada
  reemplazos      quién suele entrar por él (para el suplente de oro) y a quién suele reemplazar
  tasas por 90    remates, a puerta, faltas recibidas y cometidas, pases: últimos 10 del equipo + temporada +
                  anterior, encogidas hacia la media de su posición (JUG_K_MIN)
  amarillas por falta, para las tarjetas por jugador

Bajas (`partido["bajas"]`): el ausente sale del grupo; su puesto lo hereda el suplente que más veces entró por él
(o el de su posición con más titularidades), y su volumen se reparte solo entre los que juegan (asignación
proporcional en la simulación). Si hay partidos medidos sin él (`con_sin` en base.py), se usan para corregir el
volumen del equipo y la tasa de cada compañero, encogidos con CON_SIN_K.
"""
from collections import defaultdict

from . import params as P

GRUPO = {"POR": "POR", "DFC": "DEF", "LI": "DEF", "LD": "DEF", "CAR": "DEF",
         "MCD": "MED", "MC": "MED", "MCO": "MED", "MI": "MED", "MD": "MED",
         "EI": "ATA", "ED": "ATA", "DC": "ATA", "SD": "ATA"}


def grupo(pos):
    return GRUPO.get(pos, "MED")


def medias_posicion(db):
    """Tasa por 90 de cada grupo de posición en la liga (prior de los jugadores con pocos minutos)."""
    tot = defaultdict(lambda: {"min": 0, **{s: 0.0 for s in P.STATS_JUGADOR}, "amarillas": 0.0})
    for js in db["jugadores"].values():
        for j in js.values():
            g = grupo(j["pos"])
            for b in (j["act"], j["ant"]):
                tot[g]["min"] += b["min"]
                for s in P.STATS_JUGADOR:
                    tot[g][s] += b[s]
                tot[g]["amarillas"] += b["amarillas"]
    out = {}
    for g, t in tot.items():
        m = t["min"] or 1
        out[g] = {s: t[s] * 90 / m for s in P.STATS_JUGADOR}
        out[g]["amarillas"] = t["amarillas"] * 90 / m
    for g in ("POR", "DEF", "MED", "ATA"):
        out.setdefault(g, {**{s: 0.5 for s in P.STATS_JUGADOR}, "pases": 35.0, "amarillas": 0.15})
    return out


def _tasa(j, s, prior):
    """Últimos 10 (peso doble) + temporada + anterior (0,5), encogido hacia la posición con JUG_K_MIN minutos."""
    num = 0.0
    den = 0.0
    for b, w in ((j["u10"], 1.0), (j["act"], 1.0), (j["ant"], 0.5)):
        num += w * b.get(s, 0)
        den += w * b["min"]
    if den <= 0:
        return prior, 0
    k = P.JUG_K_MIN
    return (num * 90 + prior * k) / (den + k), den


def _stats_salida(xs):
    if not xs:
        return {"media": 75.0, "de": 14.0, "p90": 0.45, "n": 0}
    n = len(xs)
    completos = sum(1 for x in xs if x >= 90)
    sal = [x for x in xs if x < 90]
    media = sum(sal) / len(sal) if sal else 80.0
    var = sum((x - media) ** 2 for x in sal) / len(sal) if len(sal) > 1 else 144.0
    # encogido hacia el promedio de liga (45% completa, sale ~72')
    w = n / (n + 4)
    return {"media": round(w * media + (1 - w) * 72, 1), "de": round(max(6.0, var ** 0.5), 1),
            "p90": round(w * completos / n + (1 - w) * 0.45, 3), "n": n}


def preparar_equipo(db, partido, eq):
    """Lista de jugadores disponibles con participación y tasas, XI previsto, bajas e impacto de cada baja."""
    pos_m = medias_posicion(db)
    js = db["jugadores"].get(eq, {})
    al = (partido.get("alineaciones") or {})
    estado = al.get("estado")
    xi_dado = (al.get(eq) or {}).get("titulares")
    banco_dado = (al.get(eq) or {}).get("banco")
    bajas = {b["jugador"]: b for b in (partido.get("bajas") or {}).get(eq, [])}
    out_ids = {jid for jid, j in js.items() if j["nombre"] in bajas or jid in bajas}
    dudas = {jid: bajas.get(j["nombre"], bajas.get(jid, {})).get("p_juega", 0.0) for jid, j in js.items() if jid in out_ids}

    # últimos 5 partidos del equipo: una baja que ya no jugaba en ellos ya está descontada en la forma reciente
    ult5 = {x["id"] for x in (db["equipos"].get(eq) or {}).get("partidos", [])[-5:]}
    jug = []
    for jid, j in js.items():
        if j["convocado_u10"] == 0 and j["act"]["pj"] == 0:
            continue   # ya no está en el equipo (o nunca jugó esta temporada ni en los últimos 10)
        g = grupo(j["pos"])
        tasas = {}
        mins_vistos = 0
        for s in P.STATS_JUGADOR:
            tasas[s], mins_vistos = _tasa(j, s, pos_m[g][s])
        am90, _ = _tasa(j, "amarillas", pos_m[g]["amarillas"])
        faltas90 = max(0.05, tasas["faltas_cometidas"])
        n10 = max(1, j["convocado_u10"])
        p_tit = j["titular_u10"] / 10 if j["convocado_u10"] else 0.0
        entradas = len(j["min_entrada"][-10:])
        jug.append({
            "id": jid, "nombre": j["nombre"], "pos": j["pos"], "grupo": g, "lado": j.get("lado", "centro"),
            "dorsal": j.get("dorsal"),
            "p_titular": round(min(0.97, p_tit), 3), "titular_u10": j["titular_u10"], "convocado_u10": j["convocado_u10"],
            "salida": _stats_salida(j["min_salida"][-15:]),
            "p_entra": round(min(0.9, entradas / n10), 3) if entradas else 0.05,
            "min_entrada": round(sum(j["min_entrada"][-10:]) / entradas, 1) if entradas else 70.0,
            "reemplazado_por": j.get("reemplazado_por", {}), "reemplaza_a": j.get("reemplaza_a", {}),
            "tasas90": {s: round(v, 3) for s, v in tasas.items()},
            "amarilla_por_falta": round(min(0.45, am90 / faltas90 * 0.85), 4),
            "amarillas90": round(am90, 3), "min_vistos": mins_vistos,
            "baja": jid in out_ids, "p_juega": dudas.get(jid, 1.0),
            "con_sin": j.get("con_sin"),
            "reciente": round(sum(1 for x in j["partidos"] if x["id"] in ult5 and x["min"] > 0) / max(1, len(ult5)), 2),
            "ultimos": j["partidos"][-10:],
        })

    by_id = {x["id"]: x for x in jug}
    by_name = {x["nombre"]: x for x in jug}

    def buscar(k):
        return by_id.get(k) or by_name.get(k)

    disponibles = [x for x in jug if not x["baja"] or x["p_juega"] > 0]
    # ---- XI previsto
    if xi_dado:
        xi = [buscar(k) for k in xi_dado if buscar(k)]
        for x in jug:
            x["p_titular"] = 0.0
        p_xi = 1.0 if estado == "oficial" else 0.9
        for x in xi:
            x["p_titular"] = p_xi
        if banco_dado:
            for k in banco_dado:
                b = buscar(k)
                if b and b not in xi:
                    b["p_titular"] = 0.0 if estado == "oficial" else 0.08
    else:
        xi = _xi_por_frecuencia(disponibles)
    # ---- herederos de cada baja
    impacto = []
    xi_habitual = sorted(jug, key=lambda x: -x["p_titular"])[:11]
    tot_hab = {s: sum(x["tasas90"][s] * max(0.3, x["p_titular"]) for x in xi_habitual) or 1 for s in ("remates", "pases")}
    for x in jug:
        if not x["baja"]:
            continue
        her = _heredero(x, disponibles, xi, buscar)
        p_baja_tit = x["p_titular"]
        x["p_titular"] = round(x["p_titular"] * x["p_juega"], 3)
        if her is not None and not xi_dado:
            # el heredero gana la titularidad que pierde el ausente
            her["p_titular"] = round(min(0.95, her["p_titular"] + p_baja_tit * (1 - x["p_juega"])), 3)
            her["hereda_de"] = x["nombre"]
        impacto.append({"jugador": x["nombre"], "pos": x["pos"], "p_juega": x["p_juega"],
                        "motivo": (bajas.get(x["nombre"]) or bajas.get(x["id"]) or {}).get("motivo", "baja"),
                        "era_titular": round(p_baja_tit, 2), "heredero": her["nombre"] if her else None,
                        "heredero_id": her["id"] if her else None, "con_sin": x.get("con_sin"),
                        "tasas90": x["tasas90"], "reciente": x["reciente"],
                        "_share": {s: round(x["tasas90"][s] * max(0.3, p_baja_tit) / tot_hab[s], 4) for s in ("remates", "pases")}})
    if not xi_dado:
        xi = _xi_por_frecuencia([x for x in jug if x["p_titular"] > 0 and (not x["baja"] or x["p_juega"] > 0)])
    xi_ids = [x["id"] for x in xi]
    jugadores_ok = [x for x in jug if not (x["baja"] and x["p_juega"] <= 0)]
    de = db["equipos"].get(eq) or {}
    # pases acertados / totales del equipo, encogido hacia la media de Serie A (~0,84) con 3000 pases de prior
    prec = (de.get("pases_ok", 0) + 0.84 * 3000) / (de.get("pases_tot", 0) + 3000)
    return {"equipo": eq, "jugadores": jugadores_ok, "xi": xi_ids, "estado_alineacion": estado or "prevista (últimos 10)",
            "bajas": impacto, "precision_pase": round(prec, 4)}


def _xi_por_frecuencia(cands):
    """XI más probable: 1 portero + los 10 de campo con más p_titular."""
    pors = sorted([x for x in cands if x["grupo"] == "POR"], key=lambda x: -x["p_titular"])
    campo = sorted([x for x in cands if x["grupo"] != "POR"], key=lambda x: -x["p_titular"])
    return pors[:1] + campo[:10]


def _heredero(baja, disponibles, xi, buscar):
    """Quién toma el puesto: el que más veces entró por él; si no, el de su grupo con más titularidades fuera del XI."""
    xi_ids = {x["id"] for x in xi}
    cands = sorted(baja["reemplazado_por"].items(), key=lambda kv: -kv[1])
    for k, _ in cands:
        h = buscar(k)
        if h and not h["baja"] and h["id"] not in xi_ids:
            return h
    misma = [x for x in disponibles if x["grupo"] == baja["grupo"] and not x["baja"] and x["id"] != baja["id"] and x["id"] not in xi_ids]
    if not misma:
        misma = [x for x in disponibles if x["grupo"] == baja["grupo"] and not x["baja"] and x["id"] != baja["id"]]
    misma.sort(key=lambda x: (-(x["lado"] == baja["lado"]), -x["p_titular"], -x["min_vistos"]))
    return misma[0] if misma else None


def ajustes_bajas(prep, base_esperado):
    """Multiplicadores de volumen del equipo por sus bajas y ajustes de tasas de compañeros medidos con/sin.

    Devuelve ({stat: mult}, detalle). Volumen perdido = parte del ausente − parte del heredero, del que el equipo
    pierde BAJA_PERDIDA; si hay partidos medidos sin él, se mezcla con el cociente sin/con observado.
    """
    jug = {x["id"]: x for x in prep["jugadores"]}
    tit = [x for x in prep["jugadores"] if x["p_titular"] > 0.3]
    mult = {s: 1.0 for s in ("remates", "remates_puerta", "pases", "goles", "corners")}
    detalle = []
    for b in prep["bajas"]:
        if b["p_juega"] >= 1:
            continue
        cs = b.get("con_sin") or {}
        tot = {s: sum(x["tasas90"][s] for x in tit) or 1 for s in ("remates", "pases")}
        # la baja ya no está en `prep["jugadores"]` si p_juega=0; su tasa viene de con_sin o se aproxima
        her = jug.get(b.get("heredero_id"))
        d = {"jugador": b["jugador"], "heredero": b["heredero"], "equipo": {}}
        for s, s_tasa in (("remates", "remates"), ("remates_puerta", "remates"), ("goles", "remates"), ("pases", "pases"), ("corners", "remates")):
            eq_cs = (cs.get("equipo") or {}).get(s)
            medido = None
            w = 0.0
            if eq_cs and eq_cs["con"] > 0:
                medido = eq_cs["sin"] / eq_cs["con"]
                w = cs["n_sin"] / (cs["n_sin"] + P.CON_SIN_K)
            # sin medición: pérdida por volumen (la parte del ausente la conocemos por su peso en el XI habitual)
            share_baja = b.get("_share", {}).get(s_tasa, 0.0)
            share_her = (her["tasas90"][s_tasa] / tot[s_tasa]) if her else 0.0
            perdida = P.BAJA_PERDIDA * max(0.0, share_baja - share_her)
            teorico = 1 - perdida
            if medido is not None:
                medido = max(0.85, min(1.15, medido))   # con/sin es muy ruidoso con pocos partidos
            m = (1 - w) * teorico + w * (medido if medido is not None else teorico)
            # solo cuenta lo que el equipo no haya absorbido ya: si no jugaba en los últimos 5, su ausencia ya
            # está en la forma reciente del equipo
            m = 1 - (1 - m) * (1 - b["p_juega"]) * b.get("reciente", 1.0)
            mult[s] *= m
            d["equipo"][s] = {"mult": round(m, 3), "medido": round(medido, 3) if medido else None, "peso_medido": round(w, 2),
                              "reciente": b.get("reciente", 1.0)}
        detalle.append(d)
    # tope: las bajas no pueden mover el volumen del equipo más de un 20% en ningún sentido
    mult = {s: max(0.8, min(1.2, v)) for s, v in mult.items()}
    return mult, detalle


def companeros_con_sin(prep):
    """Ajusta las tasas por 90 de los compañeros con lo medido sin cada baja (encogido)."""
    jug = {x["id"]: x for x in prep["jugadores"]}
    cambios = []
    for b in prep["bajas"]:
        if b["p_juega"] >= 1:
            continue
        cs = b.get("con_sin") or {}
        for cid, c in (cs.get("companeros") or {}).items():
            x = jug.get(cid)
            if not x:
                continue
            n_sin = c["min_sin"] / 90
            w = n_sin / (n_sin + P.CON_SIN_K) * (1 - b["p_juega"])
            antes = dict(x["tasas90"])
            for s in P.STATS_JUGADOR:
                if c[s]["con"] > 0:
                    r = c[s]["sin"] / c[s]["con"]
                    r = max(0.6, min(1.6, r))
                    x["tasas90"][s] = round(x["tasas90"][s] * ((1 - w) + w * r), 3)
            if any(abs(x["tasas90"][s] - antes[s]) > 1e-3 for s in P.STATS_JUGADOR):
                cambios.append({"jugador": x["nombre"], "sin": b["jugador"], "antes": antes, "despues": dict(x["tasas90"])})
    return cambios
