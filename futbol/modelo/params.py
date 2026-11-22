"""Parámetros del modelo de fútbol (Serie A primero).

Igual que en model.py de la NBA: cada constante lleva el porqué. Son valores de partida razonables para Serie A,
NO calibrados todavía. Regla del proyecto: ningún cambio de parámetros entra sin backtest fuera de muestra
(log loss frente a la casa, calibración, % fuera de p10-p90).
"""

MODEL_VERSION = "futbol-0.1"

# --- Simulación -------------------------------------------------------------------------------------------
SIMS = 20000            # simulaciones por partido (semilla fija por partido, como en NBA)
MINUTOS = 90            # el añadido va dentro de los tramos 31-45+ y 76-90+ (los datos ya lo incluyen)
TRAMOS = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90)]
TRAMO_NOMBRES = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]

# Estadísticas de equipo que se simulan (las que pidió Nicolas).
STATS_EQUIPO = ["goles", "corners", "offsides", "amarillas", "rojas", "faltas", "remates", "remates_puerta", "pases"]
# Estadísticas de jugador que se simulan.
STATS_JUGADOR = ["remates", "remates_puerta", "faltas_recibidas", "faltas_cometidas", "pases"]

# --- Encogimientos (w = n/(n+K), mismo esquema que PLAYER_K / H2H_K en NBA) --------------------------------
FORMA_K = 6             # partidos: forma de los últimos 10 frente a la temporada
PRIOR_K = 8             # partidos: temporada actual frente a la anterior (prior)
JUG_K_MIN = 540         # minutos (6 partidos de 90): tasa por 90 del jugador frente a la de su posición
H2H_K = 4               # partidos H2H: peso bajo (README §3.3.6: solo 2 partidos de liga por temporada)
ARBITRO_K = 8           # partidos arbitrados: tarjetas del árbitro frente a la media de la liga
ARBITRO_ULT_K = 10      # los últimos 5 partidos del árbitro pesan como 5/(5+10) dentro de su media
ESTILO_K = 8            # partidos: reparto por zonas/tipo de ataque frente a la media de la liga
CON_SIN_K = 5           # partidos con/sin un jugador: cuánto creer el efecto medido de su baja

# --- Decaimiento temporal (Dixon-Coles) --------------------------------------------------------------------
VIDA_MEDIA_DIAS = 180   # README §3.1: vida media ~6 meses, a ajustar con backtest
PESO_XG = 0.6           # goles "efectivos" = 0,6·xG + 0,4·goles cuando hay xG

# --- Estado del marcador (por minuto, multiplicadores sobre la tasa del equipo) -----------------------------
# El que va perdiendo empuja (más remates y córners), el que gana se repliega y comete más faltas.
ESTADO = {
    #             perdiendo  empatando  ganando
    "remates":   (1.18,      1.00,      0.86),
    "corners":   (1.25,      1.00,      0.84),
    "pases":     (1.06,      1.00,      0.94),
    "faltas":    (0.95,      1.00,      1.08),
    "offsides":  (1.10,      1.00,      0.92),
}
ESTADO_DESDE_MIN = 20   # antes del 20' el marcador cambia poco el plan de juego
ROJA_PROPIO = 0.72      # tasa ofensiva del equipo con un jugador menos
ROJA_RIVAL = 1.22       # tasa ofensiva del rival del equipo con un expulsado

# --- Sobredispersión: multiplicador gamma por partido (común a los dos equipos + propio) ---------------------
# Ensanchar si más del 10% de los resultados reales cae fuera de p10-p90 (lección 1.5.2 de NBA).
GAMMA_COMUN = 25.0      # forma de la gamma común (ritmo del partido)
GAMMA_EQUIPO = 14.0     # forma de la gamma propia de cada equipo
GAMMA_EXP = {"pases": 0.25, "remates": 0.5, "faltas": 0.4, "corners": 0.7}   # fracción de la gamma por estadística

# --- Tarjetas ----------------------------------------------------------------------------------------------
P_SEGUNDA_AMARILLA_ROJA = 1.0   # una segunda amarilla del mismo jugador es roja (regla)
ROJA_DIRECTA_POR_FALTA = 0.0025  # rojas directas por falta (Serie A ~0,1 rojas directas por partido)
AMARILLA_SIN_FALTA = 0.55       # amarillas por partido y equipo que no vienen de una falta (protestas, pérdida de tiempo)
CAUTELA_FALTAS = 0.65           # el jugador amonestado comete ~35% menos faltas
CAUTELA_AMARILLA = 0.35         # y sus faltas son menos tarjeteables (evita un exceso de dobles amarillas)
DERBI_TARJETAS = 1.15           # prior del efecto derbi en tarjetas y faltas antes de medirlo con H2H
DERBI_GOLES = 0.95              # derbis algo más cerrados

# --- Localía -----------------------------------------------------------------------------------------------
LOCALIA_GOLES = 1.10    # ~+0,25 goles en Serie A; se re-estima en fuerza.py con encogimiento
LOCALIA_K = 150         # partidos de pseudo-muestra para la localía (es muy ruidosa)
LOCALIA_MIN, LOCALIA_MAX = 1.0, 1.25
NIVEL_K = 60            # goles de pseudo-muestra para el nivel goleador de la temporada en curso (fuerza.py)
NIVEL_LIGA_K = 30       # partidos-equipo de pseudo-muestra para la media de liga de la temporada en curso (base.py)
LOCALIA_OTROS = {"remates": 1.08, "corners": 1.08, "pases": 1.03, "faltas": 0.97, "amarillas": 0.92, "offsides": 1.0}

# --- Bajas -------------------------------------------------------------------------------------------------
# Parte del volumen de un ausente que el resto del equipo NO recupera (el resto se reparte solo entre los que
# juegan: así los demás suben sus números, como los minutos libres en NBA).
BAJA_PERDIDA = 0.45

# --- Suplente de oro ---------------------------------------------------------------------------------------
# Betano y otras casas: si el titular sale antes de cumplir la línea, el suplente que entra por él la continúa
# sumando lo que ya llevaba el titular. Solo aplica a titulares (si no es titular, la apuesta se anula).
SUPLENTE_ORO = True

# --- Mercado (comun/mercado.py) ----------------------------------------------------------------------------
MKT_W = 0.20            # peso del modelo en la mezcla con la casa (README §3.4: empezar entre 0,15 y 0,25)
VALUE_EV = 0.03
MIN_P = 0.50
MAX_PICKS_JORNADA = 12
MAX_PICKS_JUGADOR = 2
