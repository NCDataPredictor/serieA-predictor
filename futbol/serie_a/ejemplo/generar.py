"""Genera DATOS DE EJEMPLO (sintéticos) para probar el modelo y la web de punta a punta sin datos reales.

    python futbol/serie_a/ejemplo/generar.py

NO son datos reales: jugadores con nombres genéricos ("Delantero 9"), árbitros "Árbitro 1..15", estadísticas
inventadas con un generador aleatorio. Todo lo que sale de aquí lleva "ejemplo": true y la web lo marca con una
franja "Datos de ejemplo". Se borra cuando lleguen los datos reales (futbol/datos/).

Escribe futbol/serie_a/historico/ejemplo_*.json y futbol/serie_a/partidos/ejemplo_*.json.
"""
import json
import os
import random
from datetime import date, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
LIGA = os.path.dirname(AQUI)
EQ = ["INT", "MIL", "JUV", "NAP", "ROM", "LAZ", "ATA", "FIO", "BOL", "TOR",
      "GEN", "UDI", "LEC", "CAG", "VER", "PAR", "COM", "SAS", "PIS", "CRE"]
PLANTILLA = [("POR", "centro", "Portero"), ("POR", "centro", "Portero"),
             ("DFC", "izq", "Central"), ("DFC", "der", "Central"), ("DFC", "centro", "Central"),
             ("LI", "izq", "Lateral izquierdo"), ("LD", "der", "Lateral derecho"), ("LD", "der", "Lateral derecho"),
             ("MCD", "centro", "Pivote"), ("MC", "izq", "Interior"), ("MC", "der", "Interior"), ("MC", "centro", "Interior"),
             ("MCO", "centro", "Mediapunta"), ("EI", "izq", "Extremo izquierdo"), ("ED", "der", "Extremo derecho"),
             ("EI", "izq", "Extremo izquierdo"), ("DC", "centro", "Delantero"), ("DC", "centro", "Delantero"),
             ("DFC", "centro", "Central"), ("MC", "centro", "Interior")]
XI_IDX = [0, 2, 3, 5, 6, 8, 9, 10, 13, 14, 16]   # 4-3-3 titular
# peso de cada puesto en remates / faltas cometidas / faltas recibidas / pases
PESO = {"POR": (0.01, 0.1, 0.3, 0.6), "DFC": (0.35, 1.0, 0.6, 1.4), "LI": (0.4, 0.9, 0.8, 1.1), "LD": (0.4, 0.9, 0.8, 1.1),
        "MCD": (0.5, 1.4, 0.9, 1.6), "MC": (0.8, 1.1, 1.0, 1.4), "MCO": (1.3, 0.8, 1.4, 1.1),
        "EI": (1.6, 0.6, 1.5, 0.8), "ED": (1.6, 0.6, 1.5, 0.8), "DC": (2.6, 0.9, 1.3, 0.5)}
TRAMO_BASE = [0.14, 0.155, 0.18, 0.155, 0.17, 0.20]


def main(seed=7):
    rnd = random.Random(seed)
    equipos = {}
    for i, e in enumerate(EQ):
        nivel = 1.35 - i * 0.035 + rnd.uniform(-0.1, 0.1)
        equipos[e] = {
            "att": nivel, "def": 2.1 - nivel + rnd.uniform(-0.1, 0.1),
            "posesion": 50 + (nivel - 1) * 25 + rnd.uniform(-4, 4),
            "zonas": _norm([rnd.uniform(0.25, 0.45), rnd.uniform(0.2, 0.4), rnd.uniform(0.25, 0.45)]),
            "sit": _norm([rnd.uniform(0.55, 0.7), rnd.uniform(0.08, 0.2), rnd.uniform(0.18, 0.3), 0.025]),
            "tramos": _norm([x * rnd.uniform(0.8, 1.25) for x in TRAMO_BASE]),
            "dureza": rnd.uniform(0.85, 1.2),
            "jug": [{"id": f"{e}-{k + 1}", "nombre": f"{e} · {n} {k + 1}", "pos": pos, "lado": lado, "dorsal": k + 1,
                     "talento": rnd.uniform(0.6, 1.5)} for k, (pos, lado, n) in enumerate(PLANTILLA)],
        }
    arbitros = [(f"Árbitro {k}", rnd.uniform(0.75, 1.3)) for k in range(1, 16)]
    hist = []
    # temporada anterior completa (38 jornadas) y 12 jornadas de la actual
    for temp, inicio, jornadas in (("2025-26", date(2025, 8, 23), 38), ("2026-27", date(2026, 8, 22), 12)):
        cal = _calendario(EQ, rnd)
        for j in range(jornadas):
            f = inicio + timedelta(days=7 * j + (j // 13) * 7)
            for L, V in cal[j % len(cal)] if j < 19 else [(b, a) for a, b in cal[j % 19]]:
                hist.append(_partido(rnd, temp, f, j + 1, L, V, equipos, arbitros))
    os.makedirs(os.path.join(LIGA, "historico"), exist_ok=True)
    for temp in ("2025-26", "2026-27"):
        with open(os.path.join(LIGA, "historico", f"ejemplo_{temp}.json"), "w", encoding="utf-8") as fh:
            json.dump([p for p in hist if p["temporada"] == temp], fh, ensure_ascii=False, separators=(",", ":"))
    # partidos a predecir: jornada 13
    os.makedirs(os.path.join(LIGA, "partidos"), exist_ok=True)
    fecha = "2026-11-29"
    proximos = [
        ("INT", "JUV", "20:45", "14:45", "San Siro", "Árbitro 3", {"JUV": [{"jugador": "JUV · Delantero 17", "motivo": "lesion", "p_juega": 0.0}]}),
        ("ROM", "LAZ", "18:00", "12:00", "Stadio Olimpico", "Árbitro 7", {}),
        ("ATA", "NAP", "15:00", "09:00", "Gewiss Stadium", "Árbitro 11",
         {"NAP": [{"jugador": "NAP · Extremo derecho 15", "motivo": "sancion", "p_juega": 0.0}],
          "ATA": [{"jugador": "ATA · Mediapunta 13", "motivo": "lesion", "p_juega": 0.4}]}),
        ("MIL", "FIO", "12:30", "06:30", "San Siro", "Árbitro 1", {}),
    ]
    for L, V, hl, hb, est, arb, bajas in proximos:
        pid = f"{fecha}-{L}-{V}"
        d = {"id": pid, "ejemplo": True,
             "match": {"liga": "serie_a", "temporada": "2026-27", "jornada": 13, "fecha": fecha, "hora_local": hl, "hora_bogota": hb,
                       "local": L, "visitante": V, "estadio": est, "neutral": False, "competicion": "liga"},
             "contexto": {"arbitro": arb, "clima": {"lluvia_mm": 0.0, "viento_kmh": 8},
                          "descanso_dias": {L: 6, V: 6}, "europa_entre_semana": {L: None, V: None}},
             "alineaciones": {"estado": "probable"}, "bajas": bajas, "cuotas": {"casas": []}, "props": {}}
        with open(os.path.join(LIGA, "partidos", f"ejemplo_{pid}.json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    print(f"{len(hist)} partidos históricos de ejemplo y {len(proximos)} partidos a predecir")


def _norm(v):
    s = sum(v)
    return [x / s for x in v]


def _calendario(eqs, rnd):
    """Calendario de ida (19 jornadas) por el método del círculo."""
    e = eqs[:]
    rnd.shuffle(e)
    n = len(e)
    out = []
    for r in range(n - 1):
        j = []
        for i in range(n // 2):
            a, b = e[i], e[n - 1 - i]
            j.append((a, b) if (r + i) % 2 == 0 else (b, a))
        out.append(j)
        e = [e[0]] + [e[-1]] + e[1:-1]
    return out


def _pois(rnd, lam):
    import math
    L, k, p = math.exp(-lam), 0, 1.0
    if lam > 30:
        return max(0, int(round(rnd.gauss(lam, lam ** 0.5))))
    while True:
        p *= rnd.random()
        if p <= L:
            return k
        k += 1


def _partido(rnd, temp, fecha, jornada, L, V, E, arbitros):
    arb, arb_m = arbitros[rnd.randrange(len(arbitros))]
    derbi = {L, V} in ({"INT", "MIL"}, {"JUV", "INT"}, {"ROM", "LAZ"}, {"JUV", "TOR"})
    pid = f"{fecha.isoformat()}-{L}-{V}"
    eventos, equipos, jugadores, cambios = [], {}, {}, {}
    ritmo = rnd.gammavariate(20, 1 / 20)
    pos_l = (E[L]["posesion"] + 100 - E[V]["posesion"]) / 2 + 2
    for t, r, loc in ((L, V, True), (V, L, False)):
        a, d = E[t], E[r]
        k = (1.1 if loc else 0.92) * ritmo
        xg = 1.3 * a["att"] * d["def"] * k * (0.95 if derbi else 1)
        rem = _pois(rnd, 12.5 * a["att"] ** 0.7 * d["def"] ** 0.5 * k)
        pue = sum(1 for _ in range(rem) if rnd.random() < 0.34)
        gol = min(pue, _pois(rnd, xg))
        fal = _pois(rnd, 12.5 * a["dureza"] * (1.12 if derbi else 1))
        am = sum(1 for _ in range(fal) if rnd.random() < 0.15 * arb_m * a["dureza"]) + (1 if rnd.random() < 0.4 else 0)
        ro = 1 if rnd.random() < 0.06 * arb_m else 0
        pos = pos_l if loc else 100 - pos_l
        equipos[t] = {"goles": gol, "remates": rem, "remates_puerta": pue, "corners": _pois(rnd, 4.8 * a["att"] ** 0.6 * k),
                      "offsides": _pois(rnd, 1.8), "faltas": fal, "amarillas": am, "rojas": ro,
                      "pases": int(rnd.gauss(450 * pos / 50, 40)), "posesion": round(pos, 1), "xg": round(xg * rnd.uniform(0.8, 1.2), 2)}
        # eventos con minuto (tramos), zona y tipo de jugada
        for _ in range(rem):
            eventos.append({"min": _minuto(rnd, a["tramos"]), "equipo": t, "tipo": "remates",
                            "zona": rnd.choices(["izq", "centro", "der"], a["zonas"])[0],
                            "situacion": rnd.choices(["jugada", "contragolpe", "balon_parado", "penalti"], a["sit"])[0], "a_puerta": False})
        rem_t = [e for e in eventos if e["equipo"] == t and e["tipo"] == "remates"]
        for e in rnd.sample(rem_t, pue):
            e["a_puerta"] = True
        for s, n in (("goles", gol), ("corners", equipos[t]["corners"]), ("faltas", fal), ("amarillas", am),
                     ("rojas", ro), ("offsides", equipos[t]["offsides"])):
            for _ in range(n):
                eventos.append({"min": _minuto(rnd, a["tramos"] if s != "amarillas" else [.08, .12, .17, .16, .2, .27]), "equipo": t, "tipo": s})
        # alineación: XI habitual con rotación y lesiones al azar
        plant = a["jug"]
        xi = [plant[i] for i in XI_IDX]
        for i in range(len(xi)):
            if rnd.random() < 0.15:
                alt = [p for p in plant if p["pos"] == xi[i]["pos"] and p not in xi]
                if alt:
                    xi[i] = rnd.choice(alt)
        banco = [p for p in plant if p not in xi]
        mins = {p["id"]: (0, 90) for p in xi}
        cam = []
        candidatos = [p for p in xi if p["pos"] != "POR"]
        rnd.shuffle(candidatos)
        for p in candidatos[: rnd.randint(3, 5)]:
            m = max(46, min(89, int(rnd.gauss(70, 11))))
            misma = [b for b in banco if b["pos"] == p["pos"] or (p["pos"] in ("EI", "ED") and b["pos"] in ("EI", "ED"))]
            ent = misma[0] if misma else banco[0]
            banco.remove(ent)
            mins[p["id"]] = (0, m)
            mins[ent["id"]] = (m, 90)
            cam.append({"min": m, "sale": p["id"], "entra": ent["id"]})
        cambios[t] = cam
        en_campo = [p for p in plant if p["id"] in mins]
        js = []
        tot = {"remates": rem, "remates_puerta": pue, "faltas_cometidas": fal, "faltas_recibidas": None, "pases": equipos[t]["pases"]}
        pesos = {s: [PESO[p["pos"]][c] * (p["talento"] if s == "remates" else 1) * (mins[p["id"]][1] - mins[p["id"]][0]) / 90
                     for p in en_campo] for c, s in enumerate(["remates", "faltas_cometidas", "faltas_recibidas", "pases"])}
        rep = {s: _multi(rnd, tot[s], pesos[s]) for s in ("remates", "faltas_cometidas", "pases")}
        rep["remates_puerta"] = [0] * len(en_campo)
        idx_rem = [i for i, n in enumerate(rep["remates"]) for _ in range(n)]
        for i in rnd.sample(idx_rem, min(pue, len(idx_rem))):
            rep["remates_puerta"][i] += 1
        rep["_pesos_fr"] = pesos["faltas_recibidas"]
        am_rep = _multi(rnd, am, [x + 0.01 for x in pesos["faltas_cometidas"]])
        for i, p in enumerate(en_campo):
            e0, e1 = mins[p["id"]]
            js.append({"id": p["id"], "nombre": p["nombre"], "pos": p["pos"], "lado": p["lado"], "dorsal": p["dorsal"],
                       "titular": e0 == 0, "min_entra": e0, "min_sale": e1, "jugo": True,
                       "remates": rep["remates"][i], "remates_puerta": rep["remates_puerta"][i],
                       "faltas_cometidas": rep["faltas_cometidas"][i], "faltas_recibidas": 0, "pases": rep["pases"][i],
                       "amarillas": min(2, am_rep[i])})
        for p in banco:
            js.append({"id": p["id"], "nombre": p["nombre"], "pos": p["pos"], "lado": p["lado"], "dorsal": p["dorsal"],
                       "titular": False, "min_entra": 0, "min_sale": 0, "jugo": False,
                       **{s: 0 for s in ("remates", "remates_puerta", "faltas_cometidas", "faltas_recibidas", "pases", "amarillas")}})
        jugadores[t] = (js, rep["_pesos_fr"], [p["id"] for p in en_campo])
    # faltas recibidas = faltas del rival repartidas entre los propios
    out_j = {}
    for t, r in ((L, V), (V, L)):
        js, pesos_fr, ids = jugadores[t]
        fr = _multi(rnd, equipos[r]["faltas"], pesos_fr)
        for j in js:
            if j["id"] in ids:
                j["faltas_recibidas"] = fr[ids.index(j["id"])]
        out_j[t] = js
    eventos.sort(key=lambda e: e["min"])
    return {"id": pid, "ejemplo": True, "liga": "serie_a", "temporada": temp, "jornada": jornada, "fecha": fecha.isoformat(),
            "competicion": "liga", "local": L, "visitante": V, "arbitro": arb, "derbi": derbi,
            "equipos": equipos, "eventos": eventos, "jugadores": out_j, "cambios": cambios}


def _minuto(rnd, tramos):
    k = rnd.choices(range(6), tramos)[0]
    a = [1, 16, 31, 46, 61, 76][k]
    return rnd.randint(a, a + 14)


def _multi(rnd, n, pesos):
    out = [0] * len(pesos)
    if not pesos or sum(pesos) <= 0:
        return out
    for i in rnd.choices(range(len(pesos)), pesos, k=n):
        out[i] += 1
    return out


if __name__ == "__main__":
    main()
