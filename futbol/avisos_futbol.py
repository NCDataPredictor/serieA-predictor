"""Avisos al celular de las ligas de fútbol (OneSignal, el mismo proyecto que la NBA; tema por liga).

Lo corre .github/workflows/avisos.yml en cada push a main que cambie docs/<liga>/data/index.json:
    python -m futbol.avisos_futbol --before <sha de main antes del push>
Compara el index.json de antes y el de ahora y manda:
  · "Jornada N lista": cuando aparece una jornada nueva (dice cuándo salen sus picks) o la jornada pasa a tener picks
    (la víspera del primer partido, 7 pm Bogotá: ver build_site_futbol.HORA_PICKS).
  · "Alineaciones confirmadas": por cada partido cuyos dos equipos pasan a alineación oficial.
Solo a los suscritos con el tag de la liga (serie_a = 1). Sin el secreto ONESIGNAL_REST_API_KEY no envía nada.
A mano: python -m futbol.avisos_futbol --test "texto"
"""
import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(RAIZ, "docs", "push.json")
# Cada liga con su tag, su emoji en el título y su ícono (docs/<web>/icons/icon-192.png): así se distingue el aviso
# de un vistazo. Para una liga nueva: una entrada más aquí + su ícono.
LIGAS = {"serie-a": {"tag": "serie_a", "nombre": "Serie A", "emoji": "⚽"}}


def _cargar(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _git(ref, rel):
    try:
        out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=RAIZ, capture_output=True, check=True).stdout
        return json.loads(out.decode("utf-8"))
    except (subprocess.CalledProcessError, ValueError):
        return {}


def enviar(tag, titulo, texto, url, ident, icono=None):
    conf = _cargar(CONF, {})
    app, key = conf.get("onesignal_app_id"), os.environ.get("ONESIGNAL_REST_API_KEY")
    if not app or not key:
        print(f"[sin envío] {titulo} · {texto}")
        return
    uid = hashlib.md5(ident.encode()).hexdigest()
    payload = {"app_id": app, "target_channel": "push",
               "filters": [{"field": "tag", "key": tag, "relation": "=", "value": "1"}],
               "headings": {"en": titulo, "es": titulo}, "contents": {"en": texto, "es": texto}, "web_url": url,
               "chrome_web_icon": icono or conf.get("site", "") + "icons/icon-192.png", "firefox_icon": icono or conf.get("site", "") + "icons/icon-192.png", "web_push_topic": ident[:60],
               "idempotency_key": f"{uid[:8]}-{uid[8:12]}-4{uid[13:16]}-a{uid[17:20]}-{uid[20:32]}"}
    req = urllib.request.Request("https://api.onesignal.com/notifications", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Key {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Enviado: {titulo} → {r.read().decode()[:200]}")
    except Exception as e:  # no debe tumbar la acción
        print(f"No se pudo enviar «{titulo}»: {e} {e.read().decode(errors='replace')[:300] if hasattr(e, 'read') else ''}")


DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _cuando(iso_utc):
    """'2026-11-27T00:00Z' → 'el jueves 26, 7:00 pm' (hora de Bogotá)."""
    t = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")) - timedelta(hours=5)
    h = t.hour % 12 or 12
    return f"el {DIAS[t.weekday()]} {t.day}, {h}:{t.minute:02d} {'am' if t.hour < 12 else 'pm'}"


def avisos(web, antes, ahora):
    """Lista de (titulo, texto, ancla, ident) a partir de dos index.json."""
    cfg = LIGAS[web]
    out = []
    pa, pb = {p["id"]: p for p in antes.get("partidos", [])}, {p["id"]: p for p in ahora.get("partidos", [])}
    jornadas = sorted({p.get("jornada") for p in pb.values() if p.get("jornada") is not None})
    for j in jornadas:
        ids = [i for i, p in pb.items() if p.get("jornada") == j]
        n_ahora = sum(pb[i].get("n_picks", 0) for i in ids)
        n_antes = sum((pa.get(i) or {}).get("n_picks", 0) for i in ids)
        nueva = not any(i in pa for i in ids)
        if nueva or (n_ahora and not n_antes):
            ne = sum(pb[i].get("n_errores", 0) for i in ids)
            sale = (ahora.get("picks_salen") or {}).get(str(j))
            luego = f" · picks {_cuando(sale)}" if sale else " · picks cuando lleguen las cuotas"
            texto = f"{len(ids)} partidos simulados" + (f" · {n_ahora} picks con valor" if n_ahora else luego) + (f" · {ne} errores de cuota" if ne else "")
            out.append((f"{cfg['emoji']} {cfg['nombre']} · Jornada {j} lista", texto, "", f"{web}-j{j}-{'picks' if n_ahora else 'sim'}"))
    for i, p in pb.items():
        ofi = all(v == "oficial" for v in (p.get("alineacion") or {}).values()) and p.get("alineacion")
        antes_ofi = all(v == "oficial" for v in ((pa.get(i) or {}).get("alineacion") or {}).values()) and (pa.get(i) or {}).get("alineacion")
        if ofi and not antes_ofi:
            texto = f"{p['local']}–{p['visitante']} · {p.get('hora_bogota', '')} Bogotá. Revisa titulares y picks antes del partido" + (f" ({p.get('n_picks')} picks)." if p.get("n_picks") else ".")
            out.append((f"{cfg['emoji']} {cfg['nombre']} · Alineaciones confirmadas", texto, "#" + i, f"{web}-xi-{i}"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before")
    ap.add_argument("--test")
    a = ap.parse_args()
    site = _cargar(CONF, {}).get("site", "https://ncdatapredictor.pages.dev/")
    if a.test is not None:
        enviar("serie_a", "⚽ Serie A · NCData Predictor", a.test or "Prueba: así te llegará un aviso de la Serie A.", site + "serie-a/", "prueba-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), site + "serie-a/icons/icon-192.png")
        return
    for web, cfg in LIGAS.items():
        rel = f"docs/{web}/data/index.json"
        antes = _git(a.before, rel) if a.before and set(a.before) != {"0"} else {}
        ahora = _cargar(os.path.join(RAIZ, rel), {})
        for titulo, texto, ancla, ident in avisos(web, antes, ahora):
            enviar(cfg["tag"], titulo, texto, site + web + "/" + ancla, ident, site + web + "/icons/icon-192.png")


if __name__ == "__main__":
    main()
