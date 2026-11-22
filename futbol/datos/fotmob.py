"""Descargador de FotMob para la Serie A (fuente principal; probado desde el PC de Nicolas el 22-nov-2026).

Desde la nube FotMob está bloqueado: esto se corre en el PC Windows.

    python -m futbol.datos.fotmob historico                     # temporada actual + anterior → historico/
    python -m futbol.datos.fotmob historico --temporadas 2025/2026
    python -m futbol.datos.fotmob proximos                      # próxima jornada → partidos/
    python -m futbol.datos.fotmob proximos --jornada 13
    python -m futbol.datos.fotmob normalizar                    # rehace historico/ desde raw/ sin descargar

Lo crudo se guarda tal cual en futbol/serie_a/raw/fotmob/<matchId>.json (no se sube a git) para poder
rehacer la normalización. Va a 1 petición cada 1,5 s y solo baja los partidos que no tiene.

Estructura de las respuestas verificada el 22-nov-2026; fuentes probadas en futbol/datos/FUENTES.md.
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.modelo.contexto import nombre_derbi  # noqa: E402

LIGA_ID = 55
BASE = "https://www.fotmob.com/api/data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
DIR_LIGA = os.path.join(RAIZ, "futbol", "serie_a")
DIR_RAW = os.path.join(DIR_LIGA, "raw", "fotmob")
PAUSA = 1.5

# Nombre de FotMob → código de 3 letras (el de la web). Los que falten salen con las 3 primeras letras.
CODIGOS = {
    "Inter": "INT", "AC Milan": "MIL", "Milan": "MIL", "Juventus": "JUV", "Napoli": "NAP", "AS Roma": "ROM", "Roma": "ROM",
    "Lazio": "LAZ", "Atalanta": "ATA", "Fiorentina": "FIO", "Bologna": "BOL", "Torino": "TOR", "Genoa": "GEN",
    "Udinese": "UDI", "Lecce": "LEC", "Cagliari": "CAG", "Hellas Verona": "VER", "Verona": "VER", "Parma": "PAR",
    "Como": "COM", "Sassuolo": "SAS", "Pisa": "PIS", "Cremonese": "CRE", "Monza": "MON", "Venezia": "VEN",
    "Empoli": "EMP", "Salernitana": "SAL", "Frosinone": "FRO", "Sampdoria": "SAM", "Spezia": "SPE", "Palermo": "PAL",
    "Bari": "BAR", "Cesena": "CES", "Modena": "MOD", "Catanzaro": "CTZ", "Südtirol": "SUD", "Sudtirol": "SUD",
}
# Estadísticas de equipo: key de FotMob → nuestra estadística
STAT_EQ = {"BallPossesion": "posesion", "total_shots": "remates", "ShotsOnTarget": "remates_puerta", "corners": "corners",
           "Offsides": "offsides", "yellow_cards": "amarillas", "red_cards": "rojas", "fouls": "faltas", "passes": "pases",
           "expected_goals": "xg"}
# Por jugador: título de FotMob → nuestra estadística
STAT_JUG = {"Minutes played": "minutos", "Total shots": "remates", "Shots on target": "remates_puerta",
            "Fouls committed": "faltas_cometidas", "Was fouled": "faltas_recibidas", "Accurate passes": "pases"}
SITUACION = {"RegularPlay": "jugada", "FastBreak": "contragolpe", "FromCorner": "balon_parado", "SetPiece": "balon_parado",
             "FreeKick": "balon_parado", "ThrowInSetPiece": "balon_parado", "IndirectFreeKick": "balon_parado",
             "Penalty": "penalti"}
GRUPO_POS = {0: "POR", 1: "DEF", 2: "MED", 3: "ATA"}
# Zona del remate por la coordenada y (0-68, normalizada atacando hacia x=105). Si se comprueba que y=0 es la
# derecha del atacante (por ejemplo con los remates de un extremo izquierdo conocido), cambiar a True.
INVERTIR_Y = False


def codigo(nombre):
    return CODIGOS.get(nombre) or "".join(c for c in nombre.upper() if c.isalpha())[:3]


def temporada_nuestra(t):
    """'2026/2027' → '2026-27'."""
    a, b = t.split("/")
    return f"{a}-{b[-2:]}"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def liga(temporada=None):
    url = f"{BASE}/leagues?id={LIGA_ID}"
    if temporada:
        url += "&season=" + urllib.parse.quote(temporada, safe="")
    return _get(url)


def detalle(match_id, forzar=False):
    os.makedirs(DIR_RAW, exist_ok=True)
    f = os.path.join(DIR_RAW, f"{match_id}.json")
    if os.path.exists(f) and not forzar:
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    d = _get(f"{BASE}/matchDetails?matchId={match_id}")
    time.sleep(PAUSA)
    if (d.get("general") or {}).get("finished"):
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
    return d


# ---------------------------------------------------------------------------------------------- horas
def _ultimo_domingo(anio, mes):
    d = datetime(anio, mes + 1, 1, tzinfo=timezone.utc) - timedelta(days=1) if mes < 12 else datetime(anio, 12, 31, tzinfo=timezone.utc)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def hora_italia(utc):
    """CET/CEST sin depender de tzdata (Windows): verano del último domingo de marzo al de octubre, 01:00 UTC."""
    ini = _ultimo_domingo(utc.year, 3).replace(hour=1)
    fin = _ultimo_domingo(utc.year, 10).replace(hour=1)
    return utc + timedelta(hours=2 if ini <= utc < fin else 1)


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace(".000+", "+"))


# ------------------------------------------------------------------------------------------ normalizar
def _num(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).split(" ")[0].replace("%", "")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return 0


def _stats_periodo(c, periodo):
    out = {}
    for grupo in (((c.get("stats") or {}).get("Periods") or {}).get(periodo) or {}).get("stats", []) or []:
        for st in grupo.get("stats", []) or []:
            if st.get("type") == "title" or st.get("key") not in STAT_EQ:
                continue
            k = STAT_EQ[st["key"]]
            if k in out:
                continue   # algunas vienen repetidas en varios grupos
            raw = st.get("rawStats") or []
            vals = [(r or {}).get("value") for r in raw] if raw else st.get("stats", [None, None])
            out[k] = [_num(vals[0]), _num(vals[1])]
    return out


def _zona(y):
    if y is None:
        return None
    t = 68 / 3
    z = "izq" if y < t else ("centro" if y <= 2 * t else "der")
    if INVERTIR_Y and z != "centro":
        z = "der" if z == "izq" else "izq"
    return z


def _lado_layout(x):
    if x is None:
        return "centro"
    return "izq" if x < 0.36 else ("der" if x > 0.64 else "centro")


def _pos(grupo, lado):
    if grupo == "POR":
        return "POR"
    return {("DEF", "centro"): "DFC", ("DEF", "izq"): "LI", ("DEF", "der"): "LD",
            ("MED", "centro"): "MC", ("MED", "izq"): "MI", ("MED", "der"): "MD",
            ("ATA", "centro"): "DC", ("ATA", "izq"): "EI", ("ATA", "der"): "ED"}[(grupo, lado)]


def normalizar(d, temporada):
    """matchDetails de FotMob → formato de futbol/datos/FORMATO.md."""
    g = d["general"]
    c = d.get("content") or {}
    L, V = codigo(g["homeTeam"]["name"]), codigo(g["awayTeam"]["name"])
    id_eq = {g["homeTeam"]["id"]: L, g["awayTeam"]["id"]: V}
    utc = _utc(g["matchTimeUTCDate"])
    fecha = utc.date().isoformat()
    tot = _stats_periodo(c, "All")
    p1, p2 = _stats_periodo(c, "FirstHalf"), _stats_periodo(c, "SecondHalf")
    goles = [t.get("score", 0) for t in (d.get("header") or {}).get("teams", [{}, {}])]
    equipos = {}
    por_tiempo = {}
    for i, t in enumerate((L, V)):
        e = {k: v[i] for k, v in tot.items()}
        e["goles"] = goles[i] if i < len(goles) else 0
        if "xg" in e:
            e["xg"] = float(e["xg"])
        equipos[t] = e
        por_tiempo[t] = {"1": {k: v[i] for k, v in p1.items() if k not in ("posesion", "xg")},
                         "2": {k: v[i] for k, v in p2.items() if k not in ("posesion", "xg")}}
    # ---- jugadores
    lu = c.get("lineup") or {}
    jugadores, cambios, eventos = {L: [], V: []}, {L: [], V: []}, []
    pstats = c.get("playerStats") or {}
    info = {}
    for lado_eq, t in (("homeTeam", L), ("awayTeam", V)):
        eq = lu.get(lado_eq) or {}
        for titular, lst in ((True, eq.get("starters") or []), (False, eq.get("subs") or [])):
            for p in lst:
                grupo = GRUPO_POS.get(p.get("usualPlayingPositionId"), "MED")
                lado = _lado_layout((p.get("horizontalLayout") or {}).get("x")) if titular else "centro"
                info[str(p["id"])] = {"t": t, "titular": titular, "grupo": grupo, "lado": lado, "nombre": p.get("name"),
                                      "dorsal": _num(p.get("shirtNumber")) or None}
    # eventos de partido: cambios, tarjetas, goles
    salida, entrada = {}, {}
    marcador = [0, 0]
    for ev in ((c.get("matchFacts") or {}).get("events") or {}).get("events", []) or []:
        t = L if ev.get("isHome") else V
        m = min(90, ev.get("time") or 0)   # 45+2 llega como time=45, overloadTime=2
        tipo = ev.get("type")
        if tipo == "Substitution":
            sw = ev.get("swap") or []
            if len(sw) >= 2:
                entra, sale = str(sw[0]["id"]), str(sw[1]["id"])   # swap[0] entra, swap[1] sale (verificado)
                salida[sale] = m
                entrada[entra] = m
                cambios[t].append({"min": m, "sale": f"{t}-{sale}", "entra": f"{t}-{entra}"})
        elif tipo == "Card":
            card = ev.get("card") or ""
            pid = str(ev.get("playerId") or "")
            if card == "Yellow":
                eventos.append({"min": m, "equipo": t, "tipo": "amarillas", "jugador": f"{t}-{pid}"})
            elif card in ("Red", "YellowRed", "SecondYellow"):
                eventos.append({"min": m, "equipo": t, "tipo": "rojas", "jugador": f"{t}-{pid}"})
                salida.setdefault(pid, m)
        elif tipo == "Goal":
            ns = ev.get("newScore")
            # el equipo que suma es el que cambia en el marcador (vale también para autogoles)
            if ns and len(ns) == 2:
                t = L if ns[0] > marcador[0] else V
                marcador = list(ns)
            eventos.append({"min": m, "equipo": t, "tipo": "goles", "jugador": f"{t}-{ev.get('playerId')}"})
    # remates (con minuto, zona y situación)
    for s in ((c.get("shotmap") or {}).get("shots") or []):
        t = id_eq.get(s.get("teamId"))
        if not t:
            continue
        m = min(90, s.get("min") or 0)
        eventos.append({"min": m, "equipo": t, "tipo": "remates", "a_puerta": bool(s.get("isOnTarget")),
                        "zona": _zona(s.get("y")), "situacion": SITUACION.get(s.get("situation"), "jugada"),
                        "jugador": f"{t}-{s.get('playerId')}", "x": s.get("x"), "y": s.get("y"),
                        "xg": s.get("expectedGoals")})
    for pid, inf in info.items():
        t = inf["t"]
        ps = pstats.get(pid) or {}
        vals = {}
        for grupo in ps.get("stats") or []:
            for titulo, st in (grupo.get("stats") or {}).items():
                if titulo in STAT_JUG and STAT_JUG[titulo] not in vals:
                    vals[STAT_JUG[titulo]] = _num((st.get("stat") or {}).get("value"))
        mins = vals.get("minutos", 0)
        jugo = mins > 0
        if inf["titular"]:
            e0, e1 = 0, salida.get(pid, 90)
        else:
            e0 = entrada.get(pid, max(0, 90 - mins)) if jugo else 0
            e1 = salida.get(pid, 90) if jugo else 0
        am = sum(1 for e in eventos if e["tipo"] == "amarillas" and e.get("jugador") == f"{t}-{pid}")
        jugadores[t].append({"id": f"{t}-{pid}", "nombre": inf["nombre"], "pos": _pos(inf["grupo"], inf["lado"]),
                             "lado": inf["lado"], "dorsal": inf["dorsal"], "titular": inf["titular"],
                             "min_entra": e0, "min_sale": e1, "jugo": jugo,
                             "remates": vals.get("remates", 0), "remates_puerta": vals.get("remates_puerta", 0),
                             "faltas_cometidas": vals.get("faltas_cometidas", 0), "faltas_recibidas": vals.get("faltas_recibidas", 0),
                             "pases": vals.get("pases", 0), "amarillas": am})
    ref = ((c.get("matchFacts") or {}).get("infoBox") or {}).get("Referee") or {}
    eventos.sort(key=lambda e: e["min"])
    return {"id": f"{fecha}-{L}-{V}", "fuente": "fotmob", "fuente_id": str(g.get("matchId")), "liga": "serie_a",
            "temporada": temporada, "jornada": _num(g.get("matchRound")) or None, "fecha": fecha,
            "competicion": "liga", "local": L, "visitante": V, "arbitro": ref.get("text"),
            "derbi": bool(nombre_derbi(L, V)), "equipos": equipos, "por_tiempo": por_tiempo,
            "eventos": eventos, "jugadores": jugadores, "cambios": cambios}


def arbitro_fotmob(d):
    """Promedios del árbitro que trae FotMob (solo si son de la Serie A: a veces vienen de la Serie B)."""
    ref = (((d.get("content") or {}).get("matchFacts") or {}).get("infoBox") or {}).get("Referee") or {}
    if ref.get("leagueId") != LIGA_ID:
        return {"nombre": ref.get("text")} if ref else None
    st = {x["type"]: x for x in ref.get("stats") or []}
    return {"nombre": ref.get("text"), "partidos": (st.get("matches") or {}).get("value"),
            "amarillas_pp": (st.get("yellowCards") or {}).get("value"), "liga_amarillas_pp": (st.get("yellowCards") or {}).get("average"),
            "faltas_pp": (st.get("fouls") or {}).get("value"), "rojas": (st.get("redCards") or {}).get("value"),
            "penaltis": (st.get("penalties") or {}).get("value")}


# ---------------------------------------------------------------------------------------------- comandos
def cmd_historico(temporadas):
    for temp in temporadas:
        lg = liga(temp)
        time.sleep(PAUSA)
        sel = lg["details"].get("selectedSeason", temp)
        ps = [m for m in lg["fixtures"]["allMatches"] if (m.get("status") or {}).get("finished")
              and not m["status"].get("cancelled") and not m["status"].get("awarded")]
        print(f"{sel}: {len(ps)} partidos terminados")
        for i, m in enumerate(ps, 1):
            if not os.path.exists(os.path.join(DIR_RAW, f"{m['id']}.json")):
                try:
                    detalle(m["id"])
                except Exception as e:  # noqa: BLE001
                    print(f"  {m['id']}: {e}")
                if i % 20 == 0:
                    print(f"  {i}/{len(ps)}")
    cmd_normalizar()


def cmd_normalizar():
    por_temp = {}
    for f in sorted(glob.glob(os.path.join(DIR_RAW, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        g = d.get("general") or {}
        if g.get("leagueId") != LIGA_ID or not g.get("finished"):
            continue
        utc = _utc(g["matchTimeUTCDate"])
        # temporada por fecha: de julio a junio
        a = utc.year if utc.month >= 7 else utc.year - 1
        temp = f"{a}-{str(a + 1)[-2:]}"
        try:
            por_temp.setdefault(temp, []).append(normalizar(d, temp))
        except Exception as e:  # noqa: BLE001
            print(f"{f}: no se pudo normalizar ({e})")
    os.makedirs(os.path.join(DIR_LIGA, "historico"), exist_ok=True)
    for temp, ps in por_temp.items():
        ps.sort(key=lambda p: p["fecha"])
        with open(os.path.join(DIR_LIGA, "historico", f"fotmob_{temp}.json"), "w", encoding="utf-8") as fh:
            json.dump(ps, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"historico/fotmob_{temp}.json: {len(ps)} partidos")


def cmd_proximos(jornada=None):
    lg = liga()
    time.sleep(PAUSA)
    temp = temporada_nuestra(lg["details"]["selectedSeason"])
    pend = [m for m in lg["fixtures"]["allMatches"] if not (m.get("status") or {}).get("finished") and not m["status"].get("cancelled")]
    if not pend:
        print("No quedan partidos por jugar")
        return
    j = str(jornada) if jornada else str(pend[0]["round"])
    os.makedirs(os.path.join(DIR_LIGA, "partidos"), exist_ok=True)
    for m in [x for x in pend if str(x["round"]) == j]:
        d = detalle(m["id"], forzar=True)
        c = d.get("content") or {}
        L, V = codigo(m["home"]["name"]), codigo(m["away"]["name"])
        utc = _utc(m["status"]["utcTime"])
        it, bo = hora_italia(utc), utc - timedelta(hours=5)
        lu = c.get("lineup") or {}
        al = {"estado": None}
        bajas = {L: [], V: []}
        for lado_eq, t in (("homeTeam", L), ("awayTeam", V)):
            eq = lu.get(lado_eq) or {}
            if eq.get("starters") and lu.get("lineupType") == "standard":
                al["estado"] = "oficial"
                al[t] = {"titulares": [f"{t}-{p['id']}" for p in eq["starters"]], "banco": [f"{t}-{p['id']}" for p in eq.get("subs") or []]}
            for u in eq.get("unavailable") or []:
                un = u.get("unavailability") or {}
                bajas[t].append({"jugador": f"{t}-{u['id']}", "nombre": u.get("name"),
                                 "motivo": {"injury": "lesion", "suspension": "sancion"}.get(un.get("type"), un.get("type") or "baja"),
                                 "regreso": un.get("expectedReturn"), "p_juega": 0.0})
        arb = arbitro_fotmob(d)
        pid = f"{utc.date().isoformat()}-{L}-{V}"
        out = {"id": pid, "fuente": "fotmob", "fuente_id": str(m["id"]),
               "match": {"liga": "serie_a", "temporada": temp, "jornada": int(j), "fecha": utc.date().isoformat(),
                         "hora_local": it.strftime("%H:%M"), "hora_bogota": bo.strftime("%H:%M"), "utc": m["status"]["utcTime"],
                         "local": L, "visitante": V, "estadio": (((c.get("matchFacts") or {}).get("infoBox") or {}).get("Stadium") or {}).get("name"),
                         "neutral": False, "competicion": "liga"},
               "contexto": {"arbitro": (arb or {}).get("nombre"), "arbitro_fotmob": arb, "clima": c.get("weather")},
               "alineaciones": al, "bajas": bajas, "cuotas": {"casas": []}, "props": {}}
        f = os.path.join(DIR_LIGA, "partidos", f"{pid}.json")
        # conservar lo que se haya añadido a mano (cuotas, props, alineación probable de la prensa)
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                viejo = json.load(fh)
            for k in ("cuotas", "props"):
                if viejo.get(k):
                    out[k] = viejo[k]
            if not al["estado"] and (viejo.get("alineaciones") or {}).get("estado"):
                out["alineaciones"] = viejo["alineaciones"]
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"partidos/{pid}.json · árbitro {out['contexto']['arbitro']} · bajas {len(bajas[L])}+{len(bajas[V])} · alineación {al['estado'] or 'sin publicar'}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("historico")
    h.add_argument("--temporadas", nargs="+")
    p = sub.add_parser("proximos")
    p.add_argument("--jornada", type=int)
    sub.add_parser("normalizar")
    a = ap.parse_args()
    if a.cmd == "historico":
        temps = a.temporadas
        if not temps:
            lg = liga()
            time.sleep(PAUSA)
            todas = lg.get("allAvailableSeasons") or [lg["details"]["selectedSeason"]]
            temps = todas[:2]
        cmd_historico(temps)
    elif a.cmd == "normalizar":
        cmd_normalizar()
    else:
        cmd_proximos(a.jornada)


if __name__ == "__main__":
    main()
