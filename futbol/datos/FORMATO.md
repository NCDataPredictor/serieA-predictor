# Formato normalizado de un partido jugado (`futbol/<liga>/historico/*.json`)

Cada descargador (Sofascore, 365Scores, football-data, Understat…) convierte lo que baja a este formato. El
modelo (`futbol/modelo/base.py`) solo lee esto, así que cambiar de fuente no toca el modelo. Un archivo puede
traer un partido o una lista de partidos. Campos que una fuente no trae se omiten (el modelo usa la media de la
liga en su lugar), nunca se inventan.

```json
{
  "id": "2026-11-09-INT-MIL", "liga": "serie_a", "temporada": "2026-27", "jornada": 11,
  "fecha": "2026-11-09", "competicion": "liga", "local": "INT", "visitante": "MIL",
  "arbitro": "Nombre Apellido", "derbi": true, "penaltis": 1,
  "equipos": {
    "INT": {"goles": 2, "corners": 6, "offsides": 1, "amarillas": 2, "rojas": 0, "faltas": 12,
            "remates": 15, "remates_puerta": 6, "pases": 512, "posesion": 55.0, "xg": 1.84},
    "MIL": {"...": "igual"}
  },
  "eventos": [
    {"min": 23, "equipo": "INT", "tipo": "remates", "a_puerta": true, "zona": "izq", "situacion": "jugada",
     "jugador": "INT-9", "x": 88.1, "y": 30.2},
    {"min": 24, "equipo": "INT", "tipo": "goles", "jugador": "INT-9"},
    {"min": 31, "equipo": "MIL", "tipo": "amarillas", "jugador": "MIL-4"},
    {"min": 40, "equipo": "MIL", "tipo": "corners"},
    {"min": 52, "equipo": "INT", "tipo": "faltas"},
    {"min": 60, "equipo": "MIL", "tipo": "offsides"}
  ],
  "jugadores": {
    "INT": [{"id": "INT-9", "nombre": "Nombre", "pos": "DC", "lado": "centro", "dorsal": 9,
             "titular": true, "min_entra": 0, "min_sale": 78, "jugo": true,
             "remates": 4, "remates_puerta": 2, "faltas_recibidas": 2, "faltas_cometidas": 1, "pases": 21,
             "amarillas": 0}]
  },
  "cambios": {"INT": [{"min": 78, "sale": "INT-9", "entra": "INT-19"}]}
}
```

- `tipo` de evento = nombre de la estadística de equipo (`goles`, `corners`, `offsides`, `amarillas`, `rojas`,
  `faltas`, `remates`). Un remate a puerta es un evento `remates` con `"a_puerta": true`. Sirven para la
  distribución por tramos de 15'. Si la fuente solo da totales por tiempo, se omiten esos eventos y el perfil
  del equipo se queda en el de la liga para esa estadística.
- `zona` (del lado del atacante): `izq`, `centro`, `der`. Con coordenadas (Sofascore/Understat) la saca el
  descargador: tercio del ancho del campo.
- `situacion`: `jugada`, `contragolpe`, `balon_parado` (córner, falta, saque de banda), `penalti`.
- `pos`: `POR`, `DFC`, `LI`, `LD`, `MCD`, `MC`, `MCO`, `MI`, `MD`, `EI`, `ED`, `DC`, `SD`. `lado`: `izq`, `centro`, `der`.
- Los `id` de jugador son estables entre partidos (el id de la fuente con el código del equipo delante).
- Los suplentes que no jugaron van con `"jugo": false` (cuentan como convocados).
