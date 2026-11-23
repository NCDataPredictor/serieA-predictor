"""Consenso de casas (EE. UU., Europa y Pinnacle) desde The Odds API, para medir el modelo contra el mercado.

Necesita la clave gratuita de https://the-odds-api.com en la variable ODDS_API_KEY (secreto del repo en GitHub).
Sin clave no hace nada. Plan gratis: 500 créditos/mes; cada consulta cuesta mercados × regiones (aquí 2 × 2 = 4),
así que se consulta como mucho 2 veces al día por liga (ver MIN_HORAS).

    python -m futbol.datos.oddsapi                 # serie_a

Guarda una foto por consulta en futbol/<liga>/consenso/<fecha>.json (lista de fotos con hora), y deja en la
última foto, por partido: cuotas de cada casa, mejor cuota, consenso sin margen (media de casas) y Pinnacle.
Con las fotos sucesivas se mide el CLV: si la cuota de un pick le ganó a la de cierre (última foto antes del partido).
"""
import glob
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

from futbol.datos.kambi import NOMBRES_K  # noqa: E402

SPORT = {"serie_a": "soccer_italy_serie_a"}
REGIONES = "us,eu"          # us = DraftKings, FanDuel, BetMGM…; eu = Pinnacle, Unibet, Betfair…
MERCADOS = "h2h,totals"
MIN_HORAS = 10              # no volver a consultar antes de esto, salvo que falten < 3 h para un partido (cierre)


def _sin_margen(cuotas):
    inv = [1 / c for c in cuotas]
    s = sum(inv)
    return [x / s for x in inv]


def resumen(evento, L, V):
    """Por mercado: cuotas por casa, mejor cuota y consenso sin margen. Totales: solo la línea más ofrecida."""
    casas = {}
    for bk in evento.get("bookmakers", []):
        for m in bk.get("markets", []):
            if m["key"] == "h2h":
                o = {x["name"]: x["price"] for x in m["outcomes"]}
                h, a, d = o.get(evento["home_team"]), o.get(evento["away_team"]), o.get("Draw")
                if h and a and d:
                    casas.setdefault("1x2", {})[bk["key"]] = [h, d, a]
            elif m["key"] == "totals":
                ov = {x["point"]: x["price"] for x in m["outcomes"] if x["name"] == "Over"}
                un = {x["point"]: x["price"] for x in m["outcomes"] if x["name"] == "Under"}
                for pt in ov:
                    if pt in un:
                        casas.setdefault(f"goles {pt}", {})[bk["key"]] = [ov[pt], un[pt]]
    out = {}
    for mk, porcasa in casas.items():
        if mk.startswith("goles") and len(porcasa) < 3:
            continue
        n = len(next(iter(porcasa.values())))
        probs = [_sin_margen(v) for v in porcasa.values()]
        out[mk] = {"casas": porcasa, "n": len(porcasa),
                   "mejor": [max(v[i] for v in porcasa.values()) for i in range(n)],
                   "consenso": [round(sum(p[i] for p in probs) / len(probs), 4) for i in range(n)],
                   "pinnacle": _sin_margen(porcasa["pinnacle"]) if "pinnacle" in porcasa else None}
    return out


def main(liga="serie_a"):
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        print("Sin ODDS_API_KEY: no se consulta The Odds API.")
        return
    outdir = os.path.join(RAIZ, "futbol", liga, "consenso")
    os.makedirs(outdir, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    # ¿hace falta consultar? (cada MIN_HORAS, o si hay un partido en menos de 3 h: foto de cierre)
    ultimas = sorted(glob.glob(os.path.join(outdir, "*.json")))
    ultima = None
    if ultimas:
        with open(ultimas[-1], encoding="utf-8") as fh:
            fotos = json.load(fh)
        ultima = datetime.fromisoformat(fotos[-1]["hora"].replace("Z", "+00:00")) if fotos else None
    proximos = []
    for f in glob.glob(os.path.join(RAIZ, "futbol", liga, "partidos", "*.json")):
        with open(f, encoding="utf-8") as fh:
            m = json.load(fh)["match"]
        if m.get("utc"):
            t = datetime.fromisoformat(m["utc"].replace("Z", "+00:00"))
            if t > ahora:
                proximos.append(t)
    cierre = any(t - ahora < timedelta(hours=3) for t in proximos)
    if ultima and ahora - ultima < timedelta(hours=MIN_HORAS) and not (cierre and ahora - ultima > timedelta(hours=1)):
        print(f"Última consulta {ultima:%Y-%m-%d %H:%M} UTC: todavía no toca (ahorro de créditos).")
        return
    url = (f"https://api.the-odds-api.com/v4/sports/{SPORT[liga]}/odds?apiKey={key}&regions={REGIONES}"
           f"&markets={MERCADOS}&oddsFormat=decimal")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ncdata"}), timeout=30) as r:
        datos = json.loads(r.read().decode("utf-8"))
        restantes = r.headers.get("x-requests-remaining")
    foto = {"hora": ahora.strftime("%Y-%m-%dT%H:%MZ"), "creditos_restantes": restantes, "partidos": {}}
    for ev in datos:
        L, V = NOMBRES_K.get(ev["home_team"]), NOMBRES_K.get(ev["away_team"])
        if not (L and V):
            print("Sin código:", ev["home_team"], "-", ev["away_team"])
            continue
        pid = f'{ev["commence_time"][:10]}-{L}-{V}'
        foto["partidos"][pid] = {"inicio": ev["commence_time"], **resumen(ev, L, V)}
    destino = os.path.join(outdir, ahora.strftime("%Y-%m-%d") + ".json")
    fotos = []
    if os.path.exists(destino):
        with open(destino, encoding="utf-8") as fh:
            fotos = json.load(fh)
    fotos.append(foto)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(fotos, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(foto['partidos'])} partidos con consenso · créditos restantes: {restantes}")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
