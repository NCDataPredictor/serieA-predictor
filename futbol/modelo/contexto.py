"""Contexto de un partido: lo que el modelo espera de cada equipo y el porqué (para la web).

Para cada estadística de equipo (goles, córners, fueras de lugar, amarillas, rojas, faltas, remates, remates a
puerta, pases) se arma la tasa esperada del partido como en NBA (nivel de liga × ataque propio × defensa rival ×
contexto), con estas piezas, cada una guardada en `factores` para mostrarla:

  temporada    a favor / en contra por partido, mezclado con la temporada anterior (w = pj/(pj+PRIOR_K))
  forma        últimos 10 partidos del equipo (todas las competiciones), peso FORMA_W
  localía      por estadística (LOCALIA_OTROS) y la estimada en fuerza.py para goles
  árbitro      media de tarjetas y faltas del árbitro (encogida) con más peso a sus últimos 5 partidos
  derbi / H2H  cómo se jugaron los cruces de la temporada pasada (y esta) frente a lo esperado
  estilo       por dónde ataca cada uno (izq/centro/der) y cómo (jugada, contragolpe, balón parado, penalti)
               contra por dónde y cómo le hacen daño al rival; y si contra ESTE rival atacó distinto (H2H)
  tramos       en qué tramo de 15' hace y recibe cada estadística (la "distribución" del equipo)
"""
from . import params as P
from .base import ZONAS, SITUACIONES, ESPEJO

FORMA_W = 0.35          # peso de los últimos 10 frente a la temporada (forma ruidosa en fútbol: README §3.3.7)
TRAMO_K = 40            # eventos: perfil por tramos del equipo frente al de la liga
DERBIS = {
    frozenset(("INT", "MIL")): "Derby della Madonnina",
    frozenset(("JUV", "INT")): "Derby d'Italia",
    frozenset(("ROM", "LAZ")): "Derby della Capitale",
    frozenset(("JUV", "TOR")): "Derby della Mole",
    frozenset(("GEN", "SAM")): "Derby della Lanterna",
    frozenset(("NAP", "ROM")): "Derby del Sole",
    frozenset(("JUV", "MIL")): "Clásico",
    frozenset(("FIO", "JUV")): "Rivalidad",
    frozenset(("ATA", "BRE")): "Derby lombardo",
}


def nombre_derbi(a, b):
    return DERBIS.get(frozenset((a, b)))


def _por_partido(tot, n):
    return {s: (tot[s] / n if n else 0.0) for s in P.STATS_EQUIPO}


def _mezcla(e, liga, lado):
    """Por partido a favor ('favor') o en contra ('contra'): temporada actual + anterior + forma."""
    act = _por_partido(e[lado], e["pj"])
    niv = liga.get("nivel_temporada", {})
    ant = ({s: v * niv.get(s, 1.0) for s, v in _por_partido(e[lado + "_ant"], e["pj_ant"]).items()}
           if e["pj_ant"] else dict(liga["medias"]))
    w = e["pj"] / (e["pj"] + P.PRIOR_K)
    temp = {s: w * act[s] + (1 - w) * ant[s] for s in P.STATS_EQUIPO}
    u10 = e.get("ultimos10", [])
    if u10:
        f = {s: sum(x["favor" if lado == "favor" else "contra"][s] for x in u10) / len(u10) for s in P.STATS_EQUIPO}
        wf = FORMA_W * len(u10) / (len(u10) + P.FORMA_K) * (16 / 10)   # 10 partidos -> ~0,35
        wf = min(FORMA_W, wf)
        out = {s: (1 - wf) * temp[s] + wf * f[s] for s in P.STATS_EQUIPO}
    else:
        f, out = None, temp
    return out, {"temporada": act, "anterior": ant, "forma10": f, "w_temp": round(w, 2)}


def _ratio(x, m):
    return x / m if m > 0 else 1.0


def _shares(d, prior, n_k):
    tot = sum(d.values())
    w = tot / (tot + n_k)
    return {k: (w * (d[k] / tot if tot else 0) + (1 - w) * prior[k]) for k in d}


def _perfil(e, liga, s, lado):
    v = e["tramos_" + lado][s]
    t = sum(v)
    pl = liga["perfil_tramos"][s]
    w = t / (t + TRAMO_K)
    return [w * (v[i] / t if t else 0) + (1 - w) * pl[i] for i in range(6)]


def arbitro(db, nombre, externo=None):
    """Multiplicadores de tarjetas y faltas del árbitro + resumen (media y últimos 5)."""
    lm = db["liga"]["medias"]
    am_liga = 2 * lm["amarillas"]
    fa_liga = 2 * lm["faltas"]
    ps = db["arbitros"].get(nombre or "", [])
    if not ps and externo and externo.get("amarillas_pp") and externo.get("partidos"):
        # árbitro sin partidos en nuestro histórico: se usan los promedios de FotMob (solo si son de la Serie A)
        n = externo["partidos"]
        w = n / (n + P.ARBITRO_K)
        mult = (w * externo["amarillas_pp"] + (1 - w) * am_liga) / am_liga if am_liga else 1.0
        return {"nombre": nombre, "n": 0, "n_externo": n, "media_amarillas": externo["amarillas_pp"], "liga_amarillas": round(am_liga, 2),
                "media_amarillas_u5": None, "mult_amarillas": round(mult, 3), "mult_faltas": 1.0, "mult_rojas": 1.0,
                "ultimos5": [], "fuente": "fotmob"}
    if not ps:
        return {"nombre": nombre, "n": 0, "mult_amarillas": 1.0, "mult_faltas": 1.0, "mult_rojas": 1.0,
                "media_amarillas": None, "ultimos5": []}
    n = len(ps)
    # sus partidos de otras temporadas se llevan al nivel de la actual (2026-27 pita ~10% menos faltas)
    niv = db["liga"].get("nivel_temporada", {})
    temp = db.get("temporada")
    k = lambda x, s: x[s] * (1.0 if temp is None or x.get("temporada") == temp else niv.get(s, 1.0))
    am = sum(k(x, "amarillas") for x in ps) / n
    ro = sum(k(x, "rojas") for x in ps) / n
    fa = sum(k(x, "faltas") for x in ps) / n
    u5 = ps[-5:]
    am5 = sum(k(x, "amarillas") for x in u5) / len(u5)
    # media del árbitro con más peso a sus últimos 5 partidos, luego encogida hacia la liga
    w5 = len(u5) / (len(u5) + P.ARBITRO_ULT_K)
    am_ref = (1 - w5) * am + w5 * am5
    w = n / (n + P.ARBITRO_K)
    mult_am = (w * am_ref + (1 - w) * am_liga) / am_liga if am_liga else 1.0
    mult_fa = (w * fa + (1 - w) * fa_liga) / fa_liga if fa_liga else 1.0
    ro_liga = 2 * lm["rojas"] or 0.2
    mult_ro = (w * ro + (1 - w) * ro_liga) / ro_liga
    return {"nombre": nombre, "n": n, "media_amarillas": round(am, 2), "media_rojas": round(ro, 2), "media_faltas": round(fa, 1),
            "media_amarillas_u5": round(am5, 2), "liga_amarillas": round(am_liga, 2),
            "mult_amarillas": round(mult_am, 3), "mult_faltas": round(mult_fa ** 0.5, 3), "mult_rojas": round(mult_ro, 3),
            "ultimos5": list(reversed(u5))}


def h2h(db, a, b):
    """Cruces entre a y b de la temporada pasada y de esta (cualquier competición), del lado de a."""
    out = []
    for p in db["partidos"]:
        if {p["local"], p["visitante"]} == {a, b}:
            out.append(p)
    return out[-4:]


def _estilo_equipo(e, liga):
    lm = liga["medias"]
    pos = e["posesion"]
    za = _shares(e["zonas_ataque"], liga["zonas"], P.ESTILO_K * 10)
    zc = _shares(e["zonas_concede"], {z: liga["zonas"][ESPEJO[z]] for z in ZONAS}, P.ESTILO_K * 10)
    sa = _shares(e["sit_ataque"], liga["situaciones"], P.ESTILO_K * 10)
    sc = _shares(e["sit_concede"], liga["situaciones"], P.ESTILO_K * 10)
    pj = max(1, e["pj"])
    return {
        "posesion": round(sum(pos) / len(pos), 1) if pos else None,
        "pases": round(e["favor"]["pases"] / pj, 0) if e["pj"] else None,
        # presión: cuánto deja pasar al rival frente a la liga (<1 = presiona más)
        "presion": round(_ratio(e["contra"]["pases"] / pj, lm["pases"]), 2) if e["pj"] else None,
        "dureza": round(_ratio((e["favor"]["faltas"] + 3 * e["favor"]["amarillas"]) / pj, lm["faltas"] + 3 * lm["amarillas"]), 2) if e["pj"] else None,
        "zonas_ataque": {k: round(v, 3) for k, v in za.items()},
        "zonas_concede": {k: round(v, 3) for k, v in zc.items()},
        "sit_ataque": {k: round(v, 3) for k, v in sa.items()},
        "sit_concede": {k: round(v, 3) for k, v in sc.items()},
    }


def _zonas_en(partidos, eq):
    """Reparto por zona y situación de los remates de `eq` en una lista de partidos (para el H2H)."""
    z = {k: 0 for k in ZONAS}
    s = {k: 0 for k in SITUACIONES}
    for p in partidos:
        for ev in p.get("eventos", []):
            if ev["tipo"] == "remates" and ev["equipo"] == eq:
                if ev.get("zona") in z:
                    z[ev["zona"]] += 1
                if ev.get("situacion") in s:
                    s[ev["situacion"]] += 1
    return z, s


def cruce_estilos(est_a, est_b, liga, h2h_ps, a):
    """Cómo ataca `a` y por dónde le hacen daño a `b`; incluye si contra `b` atacó distinto (H2H)."""
    # zonas que usará a: su reparto habitual, corrido hacia lo que hizo contra b en los H2H
    zh, sh = _zonas_en(h2h_ps, a)
    nz = sum(zh.values())
    wz = nz / (nz + 25)   # 25 remates H2H ~ 1 partido y medio
    za = {z: (1 - wz) * est_a["zonas_ataque"][z] + wz * (zh[z] / nz if nz else 0) for z in ZONAS}
    ns = sum(sh.values())
    ws = ns / (ns + 25)
    sa = {k: (1 - ws) * est_a["sit_ataque"][k] + ws * (sh[k] / ns if ns else 0) for k in SITUACIONES}
    # b concede por su banda ESPEJO de la zona de ataque de a
    ratio_z = {z: _ratio(est_b["zonas_concede"][ESPEJO[z]], liga["zonas"][z]) for z in ZONAS}
    ratio_s = {k: _ratio(est_b["sit_concede"][k], liga["situaciones"][k]) for k in SITUACIONES}
    # multiplicador del volumen de remates por el cruce (amortiguado: raíz cuadrada; empezar suave, README §3.1)
    mz = sum(za[z] * ratio_z[z] for z in ZONAS) ** 0.5
    ms = sum(sa[k] * ratio_s[k] for k in SITUACIONES) ** 0.5
    zona_fuerte = max(ZONAS, key=lambda z: za[z] * ratio_z[z])
    return {"zonas_uso": {k: round(v, 3) for k, v in za.items()}, "sit_uso": {k: round(v, 3) for k, v in sa.items()},
            "ratio_zona_rival": {k: round(v, 3) for k, v in ratio_z.items()},
            "ratio_sit_rival": {k: round(v, 3) for k, v in ratio_s.items()},
            "h2h_cambia": {"remates_h2h": nz, "peso": round(wz, 2),
                           "zonas_h2h": {k: round(zh[k] / nz, 3) for k in ZONAS} if nz else None},
            "mult_remates": round(mz * ms, 3), "zona_fuerte": zona_fuerte}


def h2h_factores(db, a, b, ps, esperado_fn):
    """Multiplicador por estadística: lo visto en los H2H frente a lo que se esperaba de esos equipos."""
    if not ps:
        return {s: 1.0 for s in P.STATS_EQUIPO}, 0
    obs = {s: 0.0 for s in P.STATS_EQUIPO}
    esp = {s: 0.0 for s in P.STATS_EQUIPO}
    for p in ps:
        for eq in (a, b):
            for s in P.STATS_EQUIPO:
                obs[s] += p["equipos"][eq].get(s, 0)
                esp[s] += esperado_fn(eq, s)
    n = len(ps)
    w = n / (n + P.H2H_K)
    return {s: round((1 - w) + w * _ratio(obs[s], esp[s]), 3) if esp[s] > 0 else 1.0 for s in P.STATS_EQUIPO}, n


def armar(db, fz_goles, partido):
    """Tasas esperadas por equipo y estadística + todo el contexto para la web."""
    m = partido["match"]
    L, V = m["local"], m["visitante"]
    neutral = m.get("neutral", False)
    liga = db["liga"]
    lm = liga["medias"]
    E = db["equipos"]
    vacio = {"pj": 0, "pj_ant": 0, "favor": {s: lm[s] for s in P.STATS_EQUIPO}, "contra": {s: lm[s] for s in P.STATS_EQUIPO},
             "favor_ant": {s: lm[s] for s in P.STATS_EQUIPO}, "contra_ant": {s: lm[s] for s in P.STATS_EQUIPO},
             "tramos_favor": {s: [0] * 6 for s in P.STATS_EQUIPO}, "tramos_contra": {s: [0] * 6 for s in P.STATS_EQUIPO},
             "zonas_ataque": {z: 0 for z in ZONAS}, "zonas_concede": {z: 0 for z in ZONAS},
             "sit_ataque": {s: 0 for s in SITUACIONES}, "sit_concede": {s: 0 for s in SITUACIONES},
             "posesion": [], "ultimos10": [], "local": {"pj": 0}, "visit": {"pj": 0}}
    eL, eV = E.get(L, vacio), E.get(V, vacio)
    fav = {}
    con = {}
    det = {}
    for t, e in ((L, eL), (V, eV)):
        fav[t], d1 = _mezcla(e, liga, "favor")
        con[t], d2 = _mezcla(e, liga, "contra")
        det[t] = {"favor": d1, "contra": d2}

    arb = arbitro(db, partido.get("contexto", {}).get("arbitro"), partido.get("contexto", {}).get("arbitro_fotmob"))
    derbi = m.get("derbi") or bool(nombre_derbi(L, V))
    ps_h2h = h2h(db, L, V)
    est = {L: _estilo_equipo(eL, liga), V: _estilo_equipo(eV, liga)}
    cruce = {L: cruce_estilos(est[L], est[V], liga, ps_h2h, L), V: cruce_estilos(est[V], est[L], liga, ps_h2h, V)}

    def base(t, s):
        r = V if t == L else L
        if lm[s] <= 0:
            return 0.0
        return lm[s] * _ratio(fav[t][s], lm[s]) * _ratio(con[r][s], lm[s])

    h2h_mult, n_h2h = h2h_factores(db, L, V, ps_h2h, base)
    gl, gv = fz_goles(L, V, neutral)
    esperado = {}
    factores = {}
    for t in (L, V):
        es_local = t == L and not neutral
        esp = {}
        fac = {}
        for s in P.STATS_EQUIPO:
            x = base(t, s)
            f = {"base": round(x, 3)}
            if s in P.LOCALIA_OTROS and not neutral:
                lo = P.LOCALIA_OTROS[s]
                k = lo if es_local else 1 / lo
                x *= k
                f["localia"] = round(k, 3)
            if s in ("amarillas",):
                x *= arb["mult_amarillas"]
                f["arbitro"] = arb["mult_amarillas"]
            if s == "rojas":
                x *= arb["mult_rojas"]
                f["arbitro"] = arb["mult_rojas"]
            if s == "faltas":
                x *= arb["mult_faltas"]
                f["arbitro"] = arb["mult_faltas"]
            if derbi and s in ("amarillas", "faltas", "rojas") and n_h2h == 0:
                x *= P.DERBI_TARJETAS
                f["derbi"] = P.DERBI_TARJETAS
            if s in ("remates", "remates_puerta", "corners"):
                mz = cruce[t]["mult_remates"]
                x *= mz
                f["estilo"] = mz
            hm = h2h_mult.get(s, 1.0)
            if hm != 1.0:
                x *= hm
                f["h2h"] = hm
            esp[s] = x
            fac[s] = f
        # Goles: fuerza (Dixon-Coles con decaimiento, ya incluye la forma), con el cruce de estilos y el derbi.
        g = gl if t == L else gv
        g *= cruce[t]["mult_remates"] ** 0.5
        if derbi:
            g *= P.DERBI_GOLES
        g *= h2h_mult.get("goles", 1.0) ** 0.5
        esp["goles"] = g
        fac["goles"] = {"fuerza": round(gl if t == L else gv, 3), "estilo": round(cruce[t]["mult_remates"] ** 0.5, 3),
                        **({"derbi": P.DERBI_GOLES} if derbi else {}), "h2h": round(h2h_mult.get("goles", 1.0) ** 0.5, 3)}
        esperado[t] = esp
        factores[t] = fac

    # Perfil por tramos de 15' de cada estadística en ESTE partido: lo que hace el equipo y lo que concede el rival.
    perfiles = {}
    for t in (L, V):
        e, er = (eL, eV) if t == L else (eV, eL)
        perfiles[t] = {}
        for s in P.STATS_EQUIPO:
            pf = _perfil(e, liga, s, "favor")
            pc = _perfil(er, liga, s, "contra")
            g = [(pf[i] * pc[i]) ** 0.5 for i in range(6)]
            tot = sum(g) or 1
            perfiles[t][s] = [x / tot for x in g]

    tramos_hist = {}
    for t, e in ((L, eL), (V, eV)):
        pj = max(1, e["pj"] + 0.6 * e["pj_ant"])
        tramos_hist[t] = {"favor": {s: [round(x / pj, 3) for x in e["tramos_favor"][s]] for s in P.STATS_EQUIPO},
                          "contra": {s: [round(x / pj, 3) for x in e["tramos_contra"][s]] for s in P.STATS_EQUIPO}}

    return {
        "esperado": esperado, "factores": factores, "perfiles": perfiles, "tramos_hist": tramos_hist,
        "arbitro": arb, "derbi": nombre_derbi(L, V) if derbi else None, "estilos": est, "cruce": cruce,
        "h2h": {"n": n_h2h, "mult": h2h_mult, "partidos": [_h2h_row(p) for p in ps_h2h]},
        "forma": {L: eL.get("ultimos10", []), V: eV.get("ultimos10", [])},
        "detalle_tasas": det,
        "liga": {"medias": {s: round(v, 2) for s, v in lm.items()}, "zonas": liga["zonas"], "situaciones": liga["situaciones"]},
    }


def _h2h_row(p):
    return {"fecha": p["fecha"], "temporada": p["temporada"], "competicion": p.get("competicion", "liga"),
            "local": p["local"], "visitante": p["visitante"],
            "equipos": {k: {s: v.get(s, 0) for s in P.STATS_EQUIPO} for k, v in p["equipos"].items()},
            "arbitro": p.get("arbitro")}
