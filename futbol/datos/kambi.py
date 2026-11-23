"""Cuotas de Kambi (motor de Unibet, 888 y otras casas) para la Serie A: fuente accesible sin el PC.

Betano solo se puede leer desde el PC de Nicolas. Kambi publica sus cuotas en un JSON público (sin clave) con casi
los mismos mercados de equipo: goles, córners, tarjetas, remates, remates a puerta, faltas y fueras de lugar, total y
por equipo. Se guarda en el mismo formato que el extracto de Betano (futbol/datos/betano.py), así build_site_futbol
lo usa igual:

    python -m futbol.datos.kambi                    # todos los partidos de futbol/serie_a/partidos/ que no empezaron
    python -m futbol.datos.kambi --forzar           # reemplaza también extractos de Betano (por defecto se respetan)

Salida: futbol/serie_a/cuotas/<id>.json con "casa": "Kambi (Unibet)". Si ya hay un extracto de Betano de ese
partido se deja (es la casa de Nicolas) salvo --forzar.
"""
import argparse
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.betano import NOMBRES  # noqa: E402

BASE = "https://eu-offering-api.kambicdn.com/offering/v2018/ub"
Q = "lang=en_GB&market=ES"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
LIGAS = {"serie_a": "football/italy/serie_a"}
CASA = "Kambi (Unibet)"

# Nombres en inglés de Kambi que no están en betano.NOMBRES
NOMBRES_K = {**NOMBRES, "Inter Milan": "INT", "AC Milan": "MIL", "Hellas Verona": "VER", "Genoa": "GEN", "Bologna": "BOL",
             "AS Roma": "ROM", "SS Lazio": "LAZ", "SSC Napoli": "NAP", "Parma": "PAR", "Como": "COM", "Pisa": "PIS",
             "Monza": "MON", "Venezia": "VEN", "Frosinone": "FRO", "Fiorentina": "FIO", "Atalanta": "ATA"}

# Mercado (inglés de Kambi, sin el sufijo "(Settled using Opta data)") → nombre de mercado del extracto (como Betano)
MERCADOS = {"Total Goals": "Goles totales Más/Menos", "Total Corners": "Tiros de esquina Menos/Más",
            "Total Cards": "Tarjetas Totales Más/Menos", "Total Shots on Target": "Tiros al Arco",
            "Total Shots": "Remates totales", "Total Fouls conceded": "Total de Faltas Cometidas",
            "Total Offsides": "Total de Fueras de lugar"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def eventos(liga="serie_a"):
    d = _get(f"{BASE}/listView/{LIGAS[liga]}/all/matches.json?{Q}&useCombined=true")
    out = []
    for e in d.get("events", []):
        ev = e["event"]
        L, V = NOMBRES_K.get(ev.get("homeName")), NOMBRES_K.get(ev.get("awayName"))
        out.append({"id": ev["id"], "local": L, "visitante": V, "nombre": ev.get("name"), "inicio": ev.get("start"),
                    "home": ev.get("homeName"), "away": ev.get("awayName")})
    return out


def extracto(ev):
    """Extracto en el formato de betano.py a partir de las ofertas del evento."""
    d = _get(f"{BASE}/betoffer/event/{ev['id']}.json?{Q}&includeParticipants=true")
    mk = {}
    for b in d.get("betOffers", []):
        crit = (b.get("criterion") or {}).get("englishLabel", "")
        tipo = (b.get("betOfferType") or {}).get("englishName", "")
        oc = b.get("outcomes") or []
        if any(o.get("status") not in (None, "OPEN") for o in oc):
            continue
        if crit == "Full Time" and tipo == "Match" and len(oc) == 3:
            orden = {"OT_ONE": 0, "OT_CROSS": 1, "OT_TWO": 2}
            v = [None] * 3
            for o in oc:
                if o.get("type") in orden:
                    v[orden[o["type"]]] = o["odds"] / 1000
            if all(v):
                mk["Resultado del partido"] = v
            continue
        if crit == "Both Teams To Score" and tipo == "Yes/No":
            s = {o.get("type"): o["odds"] / 1000 for o in oc}
            if s.get("OT_YES") and s.get("OT_NO"):
                mk["Ambos equipos anotan"] = [s["OT_YES"], s["OT_NO"]]
            continue
        if tipo != "Over/Under":
            continue
        base = crit.replace(" (Settled using Opta data)", "").strip()
        if any(x in base for x in ("Half", "Interval", "0:00")):
            continue
        quien, nombre = None, None
        for k in sorted(MERCADOS, key=len, reverse=True):   # "Total Shots on Target" antes que "Total Shots"
            if base == k:
                quien, nombre = "TOTAL", MERCADOS[k]
                break
            eq = next((base[len(k + s):].strip() for s in (" by ", " By ", " - ") if base.startswith(k + s)), None)
            if eq is not None:
                if eq in (ev["home"], ev["away"]):
                    quien, nombre = eq, MERCADOS[k]
                break
        if not nombre:
            continue
        if quien != "TOTAL":
            quien = {ev["home"]: _betano_nombre(ev["local"]), ev["away"]: _betano_nombre(ev["visitante"])}[quien]
        clave = f"{quien}|{nombre}"
        for o in oc:
            if o.get("line") is None:
                continue
            linea = str(o["line"] / 1000)
            par = mk.setdefault(clave, {}).setdefault(linea, [None, None])
            if o.get("type") == "OT_OVER":
                par[0] = o["odds"] / 1000
            elif o.get("type") == "OT_UNDER":
                par[1] = o["odds"] / 1000
    return {"capturado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "casa": CASA, "evento": ev["nombre"],
            "kambi_id": ev["id"], "mercados": mk}


def _betano_nombre(cod):
    """Nombre que betano.cuotas_equipo reconoce para ese código (el primero de NOMBRES que lo mapea)."""
    return next(n for n, c in NOMBRES.items() if c == cod)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("liga", nargs="?", default="serie_a")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    evs = eventos(a.liga)
    print(f"Kambi: {len(evs)} partidos de {a.liga}")
    sin = [e["nombre"] for e in evs if not (e["local"] and e["visitante"])]
    if sin:
        print("Equipos sin código (añadir a NOMBRES_K):", sin)
    ahora = datetime.now(timezone.utc)
    outdir = os.path.join(RAIZ, "futbol", a.liga, "cuotas")
    os.makedirs(outdir, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(RAIZ, "futbol", a.liga, "partidos", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            p = json.load(fh)
        m = p["match"]
        pid = p.get("id") or f'{m["fecha"]}-{m["local"]}-{m["visitante"]}'
        utc = m.get("utc")
        if utc and datetime.fromisoformat(utc.replace("Z", "+00:00")) <= ahora:
            continue   # ya empezó: lo publicado queda congelado
        ev = next((e for e in evs if e["local"] == m["local"] and e["visitante"] == m["visitante"]), None)
        if not ev:
            print(f"{pid}: Kambi no lo ofrece todavía")
            continue
        destino = os.path.join(outdir, pid + ".json")
        if os.path.exists(destino) and not a.forzar:
            with open(destino, encoding="utf-8") as fh:
                if (json.load(fh).get("casa") or "").startswith("Betano"):
                    print(f"{pid}: hay cuotas de Betano, se respetan")
                    continue
        x = extracto(ev)
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump(x, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"{pid}: {len(x['mercados'])} mercados de Kambi")


if __name__ == "__main__":
    main()
