"""Vigía de alineaciones: hace que el aviso "Alineaciones confirmadas" llegue a tiempo (27-nov-2026).

Problema: las alineaciones oficiales salen ~60 min antes del partido y la acción de la jornada solo las ve si corre en
esa ventana. Los cron de GitHub llegan con 1-2 h de retraso o no llegan (la jornada "cada 3 horas" corría cada 9-12 h),
así que el aviso de alineaciones no salía nunca.

Solución: esta vigía (.github/workflows/alineaciones.yml) se queda corriendo mientras haya partidos en las próximas
horas y consulta FotMob cada pocos minutos. Cuando un partido que arranca pronto tiene las dos alineaciones oficiales y
la web todavía no las tiene, lanza la acción de la jornada (workflow_dispatch): esa re-simula con los titulares,
publica y manda el aviso con los picks actualizados (futbol/avisos_futbol.py). Basta con que UN cron de la vigía
llegue antes de los partidos: la vigía cubre el resto del día sola.

    python -m futbol.vigia_alineaciones            (en Actions: GITHUB_TOKEN y GITHUB_REPOSITORY)
    python -m futbol.vigia_alineaciones --una-vez  (una sola revisión, sin esperar ni lanzar nada: para probar)
"""
import argparse
import glob
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from futbol.datos import fotmob

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIGA = "serie_a"         # carpeta futbol/<LIGA>/partidos
WEB = "serie-a"           # docs/<WEB>/data/index.json
JORNADA_YML = "jornada.yml"

HORIZONTE = timedelta(hours=5)       # partidos que la vigía espera (si no hay ninguno, termina enseguida)
VENTANA = timedelta(minutes=90)      # desde cuánto antes del partido se buscan alineaciones
PAUSA = 6 * 60                       # segundos entre revisiones
DURACION = timedelta(hours=5, minutes=40)   # tope de una corrida (Actions corta a las 6 h)


def _utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def partidos():
    """Partidos por jugar según futbol/<LIGA>/partidos: [(id, utc, fuente_id)]."""
    out = []
    for f in glob.glob(os.path.join(RAIZ, "futbol", LIGA, "partidos", "*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            out.append((d["id"], _utc(d["match"]["utc"]), str(d["fuente_id"])))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda x: x[1])


def ya_oficiales():
    """Ids de partidos que la web publicada (main en GitHub) ya muestra con las dos alineaciones oficiales."""
    rel = f"docs/{WEB}/data/index.json"
    try:
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=RAIZ, check=True, capture_output=True, timeout=60)
        idx = json.loads(subprocess.run(["git", "show", f"origin/main:{rel}"], cwd=RAIZ, check=True,
                                        capture_output=True, timeout=60).stdout.decode("utf-8"))
    except (subprocess.SubprocessError, ValueError, OSError):
        try:
            with open(os.path.join(RAIZ, rel), encoding="utf-8") as fh:
                idx = json.load(fh)
        except (OSError, ValueError):
            return set()
    return {p["id"] for p in idx.get("partidos", [])
            if p.get("alineacion") and all(v == "oficial" for v in p["alineacion"].values())}


def alineacion_oficial(fuente_id):
    """True si FotMob ya trae los titulares oficiales de los dos equipos."""
    d = fotmob._get(f"{fotmob.BASE}/matchDetails?matchId={fuente_id}")
    lu = (d.get("content") or {}).get("lineup") or {}
    return lu.get("lineupType") == "standard" and all((lu.get(k) or {}).get("starters") for k in ("homeTeam", "awayTeam"))


def lanzar_jornada():
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("[sin GITHUB_TOKEN] se lanzaría la acción de la jornada")
        return False
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/{JORNADA_YML}/dispatches",
                                 data=json.dumps({"ref": "main"}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            print("Acción de la jornada lanzada: re-simula con titulares, publica y avisa.")
            return True
    except Exception as e:
        print(f"::warning::No se pudo lanzar {JORNADA_YML}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--una-vez", action="store_true")
    a = ap.parse_args()
    inicio = datetime.now(timezone.utc)
    hechos = set()
    while True:
        ahora = datetime.now(timezone.utc)
        futuros = [p for p in partidos() if p[1] > ahora and p[0] not in hechos]
        en_horizonte = [p for p in futuros if p[1] - ahora <= HORIZONTE]
        if not en_horizonte:
            print(f"Sin partidos por vigilar en las próximas {HORIZONTE}." if not hechos else "Vigía terminada.")
            return
        cerca = [p for p in en_horizonte if p[1] - ahora <= VENTANA]
        if cerca:
            oficiales = ya_oficiales()
            nuevos = []
            for pid, utc, fid in cerca:
                if pid in oficiales:
                    hechos.add(pid)
                    continue
                try:
                    ok = alineacion_oficial(fid)
                except Exception as e:  # FotMob caído un rato: se reintenta en la próxima vuelta
                    print(f"{pid}: FotMob no respondió ({e})")
                    continue
                print(f"{ahora:%H:%M} UTC · {pid} ({utc:%H:%M} UTC): {'alineaciones oficiales' if ok else 'aún sin alineaciones'}")
                if ok:
                    nuevos.append(pid)
            if nuevos and not a.una_vez and lanzar_jornada():
                hechos.update(nuevos)
        else:
            sig = en_horizonte[0]
            print(f"{ahora:%H:%M} UTC · próximo: {sig[0]} a las {sig[1]:%H:%M} UTC")
        if a.una_vez or datetime.now(timezone.utc) - inicio + timedelta(seconds=PAUSA) > DURACION:
            return
        time.sleep(PAUSA)


if __name__ == "__main__":
    main()
