"""Cuotas de Betano Colombia → `cuotas.equipo` del JSON de cada partido.

Betano bloquea las lecturas automáticas desde la nube, así que las cuotas se leen desde el PC de Nicolas
(navegador) con el extractor de `EXTRACTOR_JS` y se guardan tal cual en `futbol/<liga>/cuotas/<id>.json`:

    {"capturado": "2026-11-22T15:40Z", "casa": "Betano",
     "mercados": {"Resultado del partido": [5.2, 4.5, 1.57], "Ambos equipos anotan": [1.5, 2.5],
                  "TOTAL|Remates totales": {"30.5": [1.8, 1.95], ...},
                  "Atalanta|Tiros de esquina Menos/Más": {"4.5": [2.25, 1.6], ...}, ...}}

`build_site_futbol` llama a `cuotas_equipo(partido, extracto)` y añade a `partido["cuotas"]["equipo"]` una fila
por línea con cuota a los dos lados. Nunca se inventa una cuota: si falta un lado, la línea no entra.
"""

# Nombre en Betano → código del equipo (el mismo que usa el histórico).
NOMBRES = {
    "Atalanta": "ATA", "Bologna FC": "BOL", "Bologna": "BOL", "Cagliari Calcio": "CAG", "Cagliari": "CAG", "Como 1907": "COM", "Como": "COM",
    "US Cremonese": "CRE", "Cremonese": "CRE", "AC Fiorentina": "FIO", "Fiorentina": "FIO", "Frosinone": "FRO", "Genoa CFC": "GEN", "Genoa": "GEN",
    "Inter de Milán": "INT", "Inter": "INT", "Juventus FC": "JUV", "Juventus": "JUV", "SS Lazio": "LAZ", "Lazio": "LAZ", "US Lecce": "LEC", "Lecce": "LEC",
    "AC Milan": "MIL", "Milan": "MIL", "AC Monza": "MON", "Monza": "MON", "SSC Napoli": "NAP", "Napoli": "NAP", "Parma Calcio 1913": "PAR", "Parma": "PAR",
    "Pisa SC": "PIS", "Pisa": "PIS", "AS Roma": "ROM", "Roma": "ROM", "US Sassuolo Calcio": "SAS", "Sassuolo": "SAS", "Torino FC": "TOR", "Torino": "TOR",
    "Udinese Calcio": "UDI", "Udinese": "UDI", "Venezia FC": "VEN", "Venezia": "VEN", "Hellas Verona": "VER", "Verona": "VER",
}

# Mercado de Betano → estadística del modelo
STAT = {
    "Goles totales Más/Menos": "goles", "Tiros de esquina Menos/Más": "corners", "Tarjetas Totales Más/Menos": "tarjetas",
    "Tiros al Arco": "remates_puerta", "Remates totales": "remates", "Total de Faltas Cometidas": "faltas",
    "Total de Fueras de lugar": "offsides",
}

# Pegar en la consola de la página del partido en betano.co (pestaña "Todo", ?bt=13) y copiar el JSON que devuelve.
EXTRACTOR_JS = r"""
(() => { const ev = window["initial_state"].data.event, out = {};
  const re = /^(.*?)(?: - )?(Goles totales Más\/Menos|Tiros de esquina Menos\/Más|Tarjetas Totales Más\/Menos|Tiros al Arco|Remates totales|Total de Faltas Cometidas|Total de Fueras de lugar)$/;
  for (const m of ev.markets) {
    if (["Resultado del partido", "Ambos equipos anotan", "Resultado Primer Tiempo"].includes(m.name)) { out[m.name] = m.selections.map(s => s.price); continue; }
    const g = m.name.match(re); if (!g) continue;
    const k = (g[1].trim() || "TOTAL") + "|" + g[2]; if (out[k] || /Primer Tiempo|Rangos|Hándicap|Segundo/.test(k)) continue;
    const o = {}; for (const s of m.selections) { const l = s.name.match(/([\d.]+)$/); if (!l) continue;
      o[l[1]] = o[l[1]] || [null, null]; o[l[1]][/^Más/.test(s.name) ? 0 : 1] = s.price; }
    if (Object.keys(o).length) out[k] = o; }
  return JSON.stringify({capturado: new Date().toISOString().slice(0, 16) + "Z", casa: "Betano", evento: ev.name, mercados: out}); })()
"""


def cuotas_equipo(partido, extracto):
    """Filas {"ambito", "stat", "linea", "over", "under", "casa"} a partir de un extracto de Betano."""
    L, V = partido["match"]["local"], partido["match"]["visitante"]
    casa = extracto.get("casa", "Betano")
    filas = []
    for clave, lineas in (extracto.get("mercados") or {}).items():
        if "|" not in clave or not isinstance(lineas, dict):
            continue
        quien, mercado = clave.split("|", 1)
        stat = STAT.get(mercado)
        if not stat:
            continue
        if quien == "TOTAL":
            ambito = "total"
        else:
            cod = NOMBRES.get(quien.strip())
            ambito = "local" if cod == L else "visitante" if cod == V else None
        if not ambito:
            continue
        for linea, par in lineas.items():
            if not par or len(par) < 2 or not par[0] or not par[1]:
                continue
            filas.append({"ambito": ambito, "stat": stat, "linea": float(linea), "over": par[0], "under": par[1], "casa": casa})
    return filas
