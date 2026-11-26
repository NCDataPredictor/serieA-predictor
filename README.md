# NCDataPredictor · portada y modelos de fútbol (empezando por Serie A)

Web estática en `docs/` (Cloudflare Pages, carpeta de salida `docs`, sin paso de build):

| Ruta | Qué es |
|---|---|
| `docs/index.html` | **Portada**: una tarjeta por modelo. NBA enlaza a su web actual (https://nba-predictor-9hf.pages.dev/). Para añadir un modelo: una entrada en `MODELOS` del script. |
| `docs/serie-a/` | **Serie A Predictor**: jornada, panel de cada partido (Resumen, Contexto, Distribución, Jugadores, Bajas). Lee `data/index.json` y `data/<id>.json`. |
| `/premier/` | **Premier League Predictor**: vive en [NCDataPredictor/premier-league-predictor](https://github.com/NCDataPredictor/premier-league-predictor); `scripts/pages_build.sh` la copia en `docs/premier/` en cada build (igual que `/nba/` y `/champions/`). |

El contexto completo del proyecto (cómo se hizo la NBA, lecciones, plan de fútbol) está en
[`futbol/CONTEXTO.md`](futbol/CONTEXTO.md).

## Flujo

```
futbol/datos/*            descargadores por fuente → futbol/serie_a/historico/*.json (formato: futbol/datos/FORMATO.md)
futbol/serie_a/partidos/  un JSON por partido a predecir: árbitro, alineación probable/oficial, bajas, cuotas, props
python -m futbol.build_site_futbol serie_a [FECHA] [--sims N]
                          → docs/serie-a/data/index.json + <id>.json
```

## El modelo (`futbol/modelo/`, versión `futbol-0.1`)

| Archivo | Qué hace |
|---|---|
| `params.py` | Todas las constantes con su porqué. **Sin calibrar**: cada cambio se justifica con backtest. |
| `base.py` | BD de contexto a partir del histórico: medias de liga, a favor/en contra por equipo (temporada, anterior, últimos 10), tramos de 15' a favor y en contra, zonas y tipos de ataque, jugadores (tasas por 90, titularidades, minutos de salida/entrada, quién entra por quién), árbitros y efecto con/sin de cada jugador. Se puede construir "hasta" cualquier fecha para backtest. |
| `fuerza.py` | Ataque/defensa por equipo: Poisson con decaimiento temporal (Dixon-Coles, vida media 180 días), goles efectivos = 0,6·xG + 0,4·goles, localía encogida y ρ de Dixon-Coles. |
| `contexto.py` | Esperado del partido por estadística: liga × ataque × defensa rival × localía × **árbitro** (media encogida, más peso a sus últimos 5) × **derbi** × **H2H** (temporada pasada y actual, peso n/(n+4)) × **cruce de estilos** (por dónde ataca cada uno contra por dónde concede el otro, cómo llega al remate y si contra ese rival atacó distinto). Perfil por tramos de cada equipo frente al rival. |
| `jugadores.py` | Participación (titular oficial > probable > últimos 10), salida y entrada, tasas por 90 encogidas hacia su posición; **bajas**: heredero del puesto, volumen perdido del equipo y compañeros corregidos con lo medido sin él. |
| `simular.py` | **Monte Carlo minuto a minuto** (20.000 sims, semilla fija): quién está en el campo, estado del marcador, rojas, tramos; remates, a puerta, goles, pases, faltas cometidas/recibidas y tarjetas **por jugador**, córners y fueras de lugar por equipo. Guarda quién entra por cada titular para el **suplente de oro**. |
| `mercados.py` | 1X2, doble oportunidad, descanso, goles, ambos marcan, marcadores, primer gol, totales y "quién hace más" de cada estadística, por tramo, y props de jugador (con y sin suplente de oro). |

Picks (`build_site_futbol.picks`): solo props con cuota real a los dos lados, mezcla con la casa
(`MKT_W = 0,20`), EV ≥ 3%, prob. ≥ 50%, máx. 2 por jugador y 12 por jornada. Si la casa ofrece suplente de oro
en esa línea, la probabilidad del modelo es la de titular + reemplazo.

Cuándo salen: los picks de una jornada se publican desde las **7 pm (Bogotá) de la víspera de su primer partido**
(`HORA_PICKS`), porque Betano y las casas colombianas abren las cuotas ≈2 días antes. Desde ahí la acción de la nube
los actualiza cada 3 h durante toda la jornada (vie–lun, o miércoles si hay atrasados); los de un partido empezado
quedan congelados. `--picks-ya` los publica antes. En la web, la barra y la portada muestran solo la jornada actual
(con sus atrasados); las jornadas ya jugadas quedan aparte en la barra, detrás de un separador, con su marcador final.

## Datos de ejemplo

Mientras llegan los datos reales, `python futbol/serie_a/ejemplo/generar.py` crea una liga **sintética**
(jugadores "Delantero 17", "Árbitro 3"…) para probar todo de punta a punta. Todo lo que sale de ahí lleva
`"ejemplo": true` y la web lo marca con una franja amarilla. Se borra cuando haya datos reales.

## Pendiente antes de publicar picks con dinero

1. Datos reales: `python -m futbol.datos.fotmob historico` y `... proximos` **desde el PC de Nicolas** (desde la nube
   las webs de fútbol están bloqueadas). Fuentes probadas en [`futbol/datos/FUENTES.md`](futbol/datos/FUENTES.md).
2. Backtest por temporadas: log loss frente a la cuota de cierre, calibración por rango, % fuera de p10–p90,
   empates simulados frente a reales.
3. Unas semanas de picks "en seco".
