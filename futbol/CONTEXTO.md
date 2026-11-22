# NCDataPredictor · Fútbol (empezando por Serie A)

Contexto para los agentes que van a construir la parte de fútbol de NCDataPredictor. Léelo completo antes de
escribir código. Resume **cómo se pensó y se construyó el modelo de la NBA** (lo que ya funciona en este repo),
**qué cambia al pasar al fútbol**, **qué factores nuevos hay que modelar** y **cómo organizar el repo y la web**
para que todo viva en el mismo sitio: una portada desde la que se entra a NBA, Serie A, Premier League, LaLiga,
Champions League y Europa League (y más ligas después).

Escrito el 22-nov-2026, con el modelo NBA en la versión 1.7.

---

## 0. Reglas de trabajo con Nicolas (aplican a todos los agentes)

- **Idioma**: todo en español (código comentado, web, mensajes, commits).
- **Cuotas decimales** siempre. Nunca asumir una cuota (en NBA se quitó el −110 por defecto): si una casa no
  trae un mercado, ese mercado no aparece.
- **Cambios de modelo**: se revisan con Nicolas antes de mergear (regla del 20-nov). Todo lo demás (datos de la
  jornada, web, scripts) se mergea solo por PR con squash.
- **Backtest antes de cambiar el modelo**: cada cambio de parámetros se justifica con un backtest fuera de
  muestra (log loss frente a la casa, calibración, unidades). Si no mejora, no entra.
- **Su casa es Betano Colombia** (también Rushbet y BetPlay). Desde la nube esas casas están bloqueadas; se leen
  desde su PC Windows (ver §6).
- Su PC de trabajo es el Windows (DESKTOP-44GLOMU), carpeta `C:\Users\Usuario 1\Documents\nba-predictor`.
  No usar el Mac.
- Hora de referencia: **Bogotá (UTC−5)**. Ojo: Serie A juega en hora de Italia (CET/CEST), 6 horas por delante
  en invierno y 7 en verano.

---

## 1. Qué es NCDataPredictor hoy (NBA)

Repo `NCDataPredictor/nba-predictor`. Web estática en `docs/` publicada por **Cloudflare Pages** en cada push a
`main` (https://nba-predictor-9hf.pages.dev). No hay servidor: los scripts de Python generan JSON y la web
(`docs/index.html`, una sola página con JS) los lee.

Pedido original del proyecto: dado un partido concreto, simular todos los escenarios posibles y sacar el
resultado más probable y los player props más probables / recomendados, al estilo de **Linemate** (props y
rachas) y **rotobot_ai** (simulaciones de partido).

### 1.1 Flujo de datos NBA

```
fuentes (nba.com/stats, B-Ref, ESPN, Covers, scoresandodds, Kambi/Betano desde el PC)
  └─> db/build_db.py            BD de rankings de los 30 equipos (ataque, defensa, play types, zonas, DvP)
  └─> build_slate.py            slates/<fecha>.json  ->  games/<fecha>_<AWAY>@<HOME>.json (un JSON por partido)
  └─> model.py                  simulación Monte Carlo de cada partido (40.000 sims, semilla fija)
  └─> build_site.py             mezcla con el mercado, filtros, picks, parlays  ->  docs/data/*.json
  └─> evaluate.py               tras la jornada: results/<fecha>.json vs lo publicado  ->  calibración, unidades
```

### 1.2 Los factores del modelo NBA (las instrucciones del proyecto) y cómo se implementó cada uno

| Factor pedido | Implementación NBA |
|---|---|
| H2H de la temporada anterior | `h2h/<temporada>.json`. Las tasas por minuto del jugador se mezclan con sus H2H contra el rival con peso `n/(n+H2H_K)`, `H2H_K=3`; cada H2H cuenta según los minutos jugados; H2H con otro equipo valen ×0,75 o nada; si cambió de rol (titular/suplente) los minutos H2H pesan 1/3. Los cruces de esta temporada salen solos de `results/`. |
| Últimos 10 partidos (completar con la temporada anterior) | Tasas por minuto mezcladas actual/anterior con `w = g/(g+PLAYER_K)`, `PLAYER_K=6`. Desde 1.7, los minutos salen de los últimos 10 partidos del equipo (`minutes.py`), detectando quién salió de la rotación y cambios de rol. |
| Rankings de ataque y defensa en todas sus variantes | `db/`: ratings ofensivo/defensivo, ritmo, tiros por zona, play types (pick and roll, aislamientos…) de ataque y concedidos, por temporada actual y anterior. `db_link.py` traduce los cruces de estilo (play type de A contra la defensa de ese play type de B) en puntos por 100 posesiones. |
| Defensa por posición (DvP) | `dvp_statpick.csv`: lo que concede cada rival a PG/SG/SF/PF/C en puntos, rebotes, asistencias, triples. Escala las tasas del jugador. |
| Bajas propias y del rival | `out`, `gtd`/`p_play` y `adj` en el slate. Los minutos libres se reparten para sumar 240; las bajas de estrellas mueven la proyección del equipo vía `adj`. `without.py` simula cada partido "si X no juega" (picks plan B). `bajas.py` saca a un jugador de la web al momento sin re-simular. |
| Back-to-back, local/visitante, récord | Ajustes de contexto en puntos por 100 posesiones (descanso, localía; sede neutral con `"neutral": true`). |
| Blowouts | La trayectoria del marcador se simula con un puente browniano de 48 min para medir la ventaja máxima; en paliza los titulares conservan `GARBAGE_CUT=0,93` de sus minutos. |
| Fichajes y cuerpo técnico nuevo | El prior de la temporada anterior se ajusta por roster y se encoge hacia la temporada actual a medida que hay partidos (`w = gp/(gp+shrink_games)`). |

### 1.3 Cómo simula el modelo NBA (resumen de `model.py`)

1. **Rating de equipo** = mezcla del rating de la temporada actual y un prior (temporada anterior ajustada por
   roster), con encogimiento por partidos jugados.
2. **Ajustes de contexto**: bajas, descanso, localía y estilo (play types vs defensa rival).
3. **Puntos esperados** = (nivel de liga + ataque propio + defensa rival + estilo) × posesiones / 100. El nivel
   de liga se mezcla con lo que se anota esta temporada (1.6: un nivel fijo inflaba los totales +6 pts).
4. **Marcador**: componente común (ritmo) + componente independiente, DE ~12 por equipo y ~13,7 de margen.
5. **Jugadores**: minutos aleatorios (DE 5,5–6, 4% de salida temprana), reparto de los 240 minutos, puntos como
   parte del marcador simulado de su equipo, y el resto de stats con Poisson-gamma (sobredispersión) escaladas
   por DvP y H2H. Así **los props de un mismo partido quedan correlacionados** con el marcador (clave para
   parlays del mismo partido).
6. **Salida**: distribución completa de cada mercado (moneyline, spread, total, props, combinadas, doble-doble),
   con percentiles para la web.

### 1.4 De la probabilidad al pick (`build_site.py`)

- **EV** = p × cuota − 1. Un pick "con valor" necesita EV ≥ +3% (`VALUE_EV`).
- **Mezcla con el mercado** (desde 1.5): `p = (1−MKT_W)·p_mercado_sin_margen + MKT_W·p_modelo`, con
  `MKT_W = 0,25`. Es la lección más importante del proyecto (ver §1.5).
- **Filtros**: probabilidad mezclada ≥ 50% (`MIN_P`); máx. 2 picks por jugador y 15 por jornada ordenados por
  EV × p; sin Unders de novatos ni de jugadores sin temporada previa; solo props (los mercados de equipo se
  muestran pero no se recomiendan).
- **Parlays**: del mismo partido solo con patas que no se pisan (comprobando la correlación en las simulaciones),
  entre partidos de 2 patas; "parlay soñador" diario (cuota 50–200) y su versión escalonada.
- **"Errores de cuota"** (1.7): reglas medidas contra la casa (A: Over de titular en líneas ≤1,5 de triples /
  asistencias / robos / tapones / pérdidas con promedio ≥ línea ×1,2; B: Over de asistencias de titular con
  promedio ≥ línea ×1,15; C: Under de suplente). Son patrones con edge comprobado, no opiniones del modelo.
- Las cuotas de EE. UU. (mejor precio entre ~6 casas, margen ~3,5%) se llevan al margen de Betano
  (`CO_OVERROUND 1,08`) para no prometer EV que en Colombia no existe.

### 1.5 Lecciones aprendidas (lo que NO hay que repetir en fútbol)

1. **El modelo solo es sobreconfiado frente al mercado.** Diagnóstico del 1-nov: el modelo decía 64%, la casa
   53,6%, la realidad 48,7%; −91 u en 955 picks. En líneas con cuota a ambos lados, el log loss del modelo (0,730)
   era peor que el de la casa (0,685) e incluso que 50/50. Desde entonces **se parte del precio de la casa y el
   modelo solo lo mueve un poco** (peso óptimo medido entre 0,05 y 0,25). En fútbol, con mercados de 1X2 muy
   eficientes, esto aplica todavía más.
2. **Simulaciones demasiado estrechas** generan probabilidades extremas falsas. Medir siempre qué porcentaje de
   resultados reales cae fuera del p10–p90 simulado (debe ser ~10% por cada lado) y ensanchar.
3. **Volumen mata.** El 30-oct salieron 787 picks (−67,7 u). Tope diario y por jugador.
4. **Los parlays del mismo partido no pueden compartir patas** (se perdían todos a la vez).
5. **EV alto con probabilidad baja no es un buen pick** (Overs 0,5 triples al 26%): piso de probabilidad.
6. **Sesgo de selección**: aunque la proyección media esté calibrada, si los picks se eligen por "mayor
   diferencia con la casa" salen casi todos del mismo lado (Unders). Medir el resultado por lado.
7. **Las rachas tipo Linemate ("8 de 10 por encima") no dan edge** por sí solas; la casa ya las ve.
8. **Los minutos/participación del jugador explican la mayor parte del error en props**, más que su eficiencia.
   En fútbol el equivalente es "¿es titular y cuántos minutos juega?" (ver §3.3).
9. **Novatos y jugadores sin historial** se subestiman: no apostar Unders contra ellos hasta tener muestra.
10. **El nivel de liga cambia entre temporadas**: no fijarlo; mezclarlo con lo que se ve esta temporada.
11. Versionar el modelo (`MODEL_VERSIONS`) y separar las unidades por versión en la web para saber qué funcionó.

### 1.6 La rutina operativa NBA

- **3:10 Bogotá** resultados de ayer (box scores ESPN) → `evaluate.py` → web.
- **11:20** picks de hoy (snapshot de BD, cuotas, props, simulación, PR + merge).
- **45 min antes del primer partido** y luego cada hora: revisión de bajas y cuotas; re-simula solo lo que cambió;
  avisos push (OneSignal) si cambian picks.
- Cada jornada queda congelada al empezar el partido: lo publicado es lo que se evalúa (historial honesto).

---

## 2. ¿Debe cambiar el modelo al pasar al fútbol?

**La filosofía se mantiene; el motor estadístico cambia.**

Se mantiene:
- Simulación Monte Carlo de cada partido con semilla fija, de la que salen *todos* los mercados de forma
  coherente (equipo y jugadores correlacionados).
- Ratings de ataque/defensa con encogimiento entre temporada actual y prior.
- Contexto del partido (bajas, descanso, localía, H2H, estilo).
- Mezcla con el mercado, filtros de picks, topes diarios, evaluación y backtest antes de cada cambio.
- Web estática alimentada por JSON y la misma experiencia (picks del día, ficha de jugador, Mis picks, Mi combinada).

Cambia (por qué el motor NBA no sirve tal cual):

| NBA | Fútbol |
|---|---|
| ~225 puntos por partido: el marcador es casi normal y la varianza relativa es baja. | ~2,6 goles por partido: eventos raros y discretos. Un gol cambia todo. Se modela con **Poisson / Dixon-Coles / binomial negativa**. |
| No hay empate. | **Tres resultados (1X2)**. Poisson independiente subestima los empates (0-0, 1-1): hace falta la corrección de Dixon-Coles (ρ) o inflar empates y calibrar. |
| Posesiones (ritmo) definen el volumen. | El volumen lo definen **tiros y xG** (goles esperados). xG es más estable que los goles para medir la fuerza real. |
| 240 minutos repartidos entre ~10 jugadores, rotación fluida. | 11 titulares, **5 cambios**, minutos muy desiguales (90 para titulares, 0–30 para suplentes). La pregunta clave es **titular sí/no** y **minuto de sustitución**. |
| Bajas conocidas por el parte oficial. | **Alineaciones oficiales ~60 min antes**; antes, alineaciones probables de la prensa. Sanciones por tarjetas. |
| Back-to-back. | **Calendario europeo entre semana** (Champions, Europa, Conference, Coppa Italia), **rotaciones**, parones de selecciones. |
| Estado del marcador poco relevante salvo palizas. | **El estado del marcador cambia el juego**: el que gana se repliega, el que pierde tira y saca córners. Hay que simular minuto a minuto. |
| Props de stats continuas (puntos, rebotes…). | Props mayormente **de conteo bajo y binarias**: marca sí/no, asistencia, tarjeta, remates, remates a puerta. |
| Árbitro casi irrelevante. | **El árbitro mueve tarjetas y penaltis** (y algo los goles). |
| Pabellón cerrado. | **Clima, viento, césped** afectan totales. |

---

## 3. Propuesta de modelo para fútbol

### 3.1 Fuerza de equipo

- **Modelo base**: ataque y defensa por equipo estimados con **Dixon-Coles con decaimiento temporal**
  (los partidos viejos pesan menos, vida media de ~6 meses a ajustar con backtest), sobre **xG** y goles
  mezclados (por ejemplo 0,6·xG + 0,4·goles, peso a calibrar). xG sin penaltis + penaltis aparte.
- **Prior entre temporadas**: temporada anterior encogida hacia la media, ajustada por fichajes y salidas
  (minutos y xG/xA que se van y llegan) y por cambio de entrenador. Igual que en NBA: `w = pj/(pj+k)`.
- **Ascendidos de Serie B**: prior por debajo de la media de Serie A (históricamente los ascendidos bajan;
  calibrar con 5–10 temporadas). Para Champions/Europa League, la fuerza entre ligas sale de **ClubElo**
  (clubelo.com, API CSV gratuita) o coeficientes UEFA.
- **Localía**: en Serie A ~+0,2/+0,3 goles; estimarla por liga y por equipo con mucho encogimiento.
- **Estilo** (análogo a play types): presión (PPDA), posesión, centros, juego directo, balón parado a favor y en
  contra. Cruces de estilo como en `db_link.py`: equipo que centra mucho contra defensa que concede de cabeza, etc.
  Empezar sin esto y añadirlo solo si el backtest lo pide.

### 3.2 Simulación del partido

Recomendado: **simulación minuto a minuto** (90 + añadido) en vez de sacar dos números de Poisson:

- Cada equipo tiene una intensidad de goles por minuto λ(t) = base × factor de estado del marcador × factor de
  rojas × factor de minuto (se marca más al final de cada tiempo).
- Con el marcador en cada minuto salen: 1X2, doble oportunidad, empate no válido, hándicap asiático y europeo,
  totales 0,5–4,5, totales por equipo, ambos marcan, resultado exacto, primer tiempo / segundo tiempo,
  descanso/final, primer y último gol, margen, portería a cero.
- **Córners**: binomial negativa por equipo, ligada al estado del marcador (el que pierde saca más).
- **Tarjetas**: base del equipo y del rival (faltas), multiplicador del árbitro, derbi/importancia, y estado
  del marcador (más tarjetas en partidos igualados y al final). Rojas con su efecto en λ del resto del partido.
- **Penaltis**: tasa por equipo × árbitro (y VAR), con su lanzador.
- Validar: frecuencia de 0-0, 1-1 y empates simulados vs reales; % fuera de p10–p90 en goles, córners y tarjetas.

### 3.3 Jugadores (props)

1. **Participación**: probabilidad de ser titular (alineación probable → oficial), minuto esperado de
   sustitución (histórico del jugador y del entrenador), probabilidad de entrar desde el banco. Igual que en NBA,
   este paso explica la mayor parte del error. Antes de la alineación oficial, los props llevan `p_titular`;
   tras la oficial, se re-simula.
2. **Reparto del volumen del equipo**: cada jugador tiene su parte de los remates y del xG del equipo por 90
   minutos jugados (y de xA / pases clave). Los goles del jugador salen de los goles simulados del equipo en los
   minutos en que está en el campo (análogo a "los puntos son parte del marcador del equipo" en NBA). Así
   **marcador y goleadores quedan correlacionados**.
3. **Mercados**: marca en cualquier momento, primer goleador, 2+ goles, asistencia, marca o asiste, remates
   (1+, 2+, 3+), remates a puerta, tarjeta amarilla, faltas cometidas/recibidas, entradas, paradas del portero,
   pases (si la casa los ofrece).
4. **Rol especial**: lanzador de penaltis (sube mucho la prob. de marcar), lanzador de córners y faltas
   (asistencias), defensores fuertes en balón parado.
5. **Defensa por zona (el DvP del fútbol)**: lo que concede el rival por zona/posición (laterales, extremos,
   delanteros centro, mediapuntas) en remates, xG y tarjetas provocadas. Escala las tasas del jugador como DvP
   escala en NBA.
6. **H2H**: mantenerlo, pero con poco peso: en fútbol hay solo 2 partidos de liga por temporada entre dos
   equipos y cambian entrenadores y plantillas. Como en NBA, medirlo con backtest antes de darle peso (en NBA el
   H2H empeoró los puntos en muchas jornadas).
7. **Últimos 10 partidos**: forma reciente con encogimiento hacia la temporada; en fútbol la forma por goles es
   muy ruidosa, usar xG/remates de los últimos partidos.

### 3.4 Del modelo al pick

- Repetir la **mezcla con el mercado** desde el día 1 (empezar con un peso del modelo bajo, ~0,15–0,25, y
  medir). La casa de Serie A en 1X2 y totales es muy eficiente; los posibles edges están más en **props de
  jugador, tarjetas, córners y en el momento de las alineaciones** (cuando la casa tarda en mover).
- Mismos filtros de partida: probabilidad ≥ 50%, EV ≥ 3%, tope por jornada y por jugador, parlays sin patas que se
  pisen. Al principio **no recomendar mercados de equipo** hasta que el backtest demuestre valor (lección 1.5).
- Medir: log loss frente a la casa sin margen, calibración por rango de probabilidad, unidades, ROI por mercado y
  por lado, **CLV** (si el pick mejoró la cuota de cierre).

---

## 4. Factores nuevos que hay que considerar en fútbol

Por orden de impacto esperado:

1. **Alineaciones**: probables (prensa italiana: Gazzetta dello Sport, Fantacalcio, Sky Sport Italia) y
   oficiales (~60 min antes). Es el equivalente de las bajas de última hora de la NBA y la mayor fuente de valor.
2. **Rotaciones por calendario**: partidos de Champions / Europa / Conference League y Coppa Italia entre
   semana; días de descanso; viajes largos (por ejemplo un jueves de Europa League en el este de Europa y
   domingo a mediodía en Italia). Es el "back-to-back" del fútbol.
3. **Bajas y sanciones**: lesiones (Transfermarkt), sanciones por acumulación de amarillas y por rojas
   (comprobar el reglamento vigente de Serie A), jugadores al límite de amarillas (algunos se cuidan).
4. **Parones de selecciones**: jugadores que vuelven tarde, lesionados o cansados (sudamericanos sobre todo).
5. **Motivación y tabla**: pelea por el título, por puestos de Champions/Europa, por no descender; equipos sin
   nada en juego al final de temporada; partidos entre semana antes de un cruce europeo importante.
6. **Árbitro**: tarjetas por partido, penaltis pitados, faltas; el árbitro de Serie A se anuncia ~2 días antes.
7. **Derbis y rivalidades**: Milán (Inter–Milan), Derby d'Italia (Juventus–Inter), Roma–Lazio, Turín, etc.
   Más tarjetas y partidos más cerrados.
8. **Cambio de entrenador**: efecto de "nuevo técnico" y cambio de estilo/sistema; el prior debe encogerse más.
9. **Clima y estado del césped**: lluvia fuerte y viento bajan totales y tiros de lejos.
10. **Estado del marcador y rojas**: se simulan dentro del partido (§3.2), no son entradas.
11. **Fichajes**: ventanas de verano e invierno (enero); medir minutos y xG/xA que entran y salen.
12. **Balón parado**: Serie A tiene mucho gol de balón parado; separar xG de jugada y de balón parado.
13. **Sede neutral / estadio compartido**: San Siro (Inter y Milan) y el Olímpico (Roma y Lazio) se comparten:
    la localía es por designación, no por estadio.

Mapa de los factores originales del proyecto al fútbol:

| Factor original | En fútbol |
|---|---|
| H2H temporada anterior | Los 2 partidos de liga + copa/Europa si los hubo; peso bajo y medido. |
| Últimos 10 partidos | xG, xGA, remates y goles de los últimos 10 (todas las competiciones, marcando cuáles). |
| Rankings ataque/defensa y variantes | xG/xGA, remates y remates a puerta a favor/en contra, goles de jugada y balón parado, córners, tarjetas, PPDA, posesión, centros. |
| PPG/APG/RPG por posición concedidos | Remates, xG, goles y asistencias concedidos por zona/posición. |
| Bajas propias y rivales | Alineaciones probables/oficiales, lesiones, sanciones. |
| Back-to-back | Días de descanso, partido europeo entre semana, viajes. |
| Local / visitante | Localía por liga y equipo (más pequeña que antes de 2020). |
| Récord victorias-derrotas | Puntos y posición en la tabla, más lo que se juega cada equipo. |
| Blowouts | Goleadas (3+ goles de diferencia) y su efecto en sustituciones tempranas. |
| Fichajes y cuerpo técnico | Ventanas de traspasos, cambio de entrenador, ascendidos. |

---

## 5. Datos: fuentes candidatas (verificar desde la nube antes de depender de ellas)

En NBA aprendimos que muchas webs bloquean el proxy de la nube (nba.com/stats, Betano, Kambi, X) y que
solo funcionan desde el PC de Nicolas. **Lo primero que debe hacer el agente de datos es probar cada fuente
desde la nube y desde el PC y anotar en la memoria del proyecto qué funciona.**

| Necesidad | Fuentes candidatas | Notas |
|---|---|---|
| Resultados y cuotas históricas (backtest) | **football-data.co.uk** (CSV por temporada: resultados, tiros, córners, tarjetas, árbitro en algunas ligas, cuotas de apertura y cierre de varias casas) | Base ideal para el backtest del modelo de equipo y la evaluación frente a la cuota de cierre. |
| xG por partido y por jugador | **Understat** (Serie A, Premier, LaLiga, Bundesliga, Ligue 1), FBref, FotMob, Sofascore | Understat cubre las 5 grandes ligas desde 2014. Comprobar qué datos avanzados mantiene FBref. |
| Fuerza entre ligas (Champions/Europa) | **ClubElo** (api.clubelo.com), coeficientes UEFA | Para comparar un equipo italiano con uno de otra liga. |
| Alineaciones probables | Fantacalcio.it, Gazzetta, Sky Sport Italia, Sportmole, RotoWire Soccer | Publicadas 1–2 días antes, actualizadas el día del partido. |
| Alineaciones oficiales | Sofascore, FotMob, ESPN, web de la Serie A | ~60 min antes del partido. |
| Lesiones y sanciones | Transfermarkt, web de la Serie A (giudice sportivo), prensa | |
| Árbitros | Web de la Serie A / AIA (designaciones), estadísticas de tarjetas por árbitro (worldfootball, footystats) | |
| Calendario | Web de la Serie A, ESPN, FotMob | Incluir copa y competiciones europeas para el descanso. |
| Clima | Open-Meteo (API gratuita) | Por coordenadas del estadio y hora del partido. |
| Cuotas Colombia | **Rushbet / BetPlay (API Kambi)** y **Betano**, desde el PC de Nicolas | En NBA ya existe `odds/fetch_co.py` (Kambi) y la lectura de Betano desde su Chrome; adaptarlos a fútbol. |
| Cuotas internacionales | OddsPortal, comparadores | Para precio de mercado y línea de cierre. |

Guardar **todo lo crudo con fecha** (`futbol/<liga>/raw/<fecha>/`) como en `db/raw/` de NBA: permite rehacer
cualquier jornada y backtestear con los datos que había en ese momento.

---

## 6. Rutina operativa propuesta para Serie A

Diferencias con NBA: la jornada se reparte de viernes a lunes (a veces entre semana), con horarios de Italia.
En hora de Bogotá (invierno) los partidos de Serie A suelen caer entre las **6:30 y las 14:45**; en verano
(horario de verano en Europa) una hora antes. Por eso **los picks deben publicarse la noche anterior**, no a
media mañana como en NBA.

Propuesta (a confirmar con Nicolas):

1. **Tras cada día de partidos**: resultados, estadísticas de jugadores, evaluación, web.
2. **Previa de la jornada (miércoles/jueves)**: actualizar ratings, simular todos los partidos de la jornada con
   alineaciones probables, publicar proyecciones y mercados de equipo.
3. **Noche anterior a cada día de partidos**: alineaciones probables actualizadas, árbitro, clima, cuotas y
   props; publicar picks.
4. **~55 min antes de cada partido**: alineación oficial → re-simular ese partido → actualizar picks y mandar
   aviso push si cambian. Es la actualización con más valor.

---

## 7. Arquitectura multi-deporte (repo y web)

### 7.1 Principios

- **Un solo repo y una sola web** (Cloudflare Pages, rama `main`, carpeta `docs/`).
- **No romper la NBA**: tiene tareas programadas diarias que llaman a scripts en la raíz del repo y usuarios con
  la web instalada como app (PWA) y picks guardados en su navegador. Mover archivos NBA es la última fase.
- Separar **lo común** (cuotas, mezcla con mercado, EV, filtros, parlays, evaluación, avisos) de **lo propio de
  cada deporte** (modelo, datos, simulación).

### 7.2 Estructura propuesta del repo

```
nba-predictor/                 (más adelante se puede renombrar el repo a "predictor"; GitHub redirige)
├── (scripts NBA en la raíz)   se quedan donde están mientras haya tareas programadas que los llamen
├── comun/                     código compartido, extraído poco a poco de build_site.py
│   ├── cuotas.py              decimal/americana, quitar margen, localizar a margen colombiano
│   ├── mercado.py             mezcla modelo-casa (MKT_W), EV, MIN_P, topes diarios
│   ├── parlays.py             combinadas sin patas compartidas, correlación desde las simulaciones
│   └── evaluar.py             log loss, calibración, unidades, CLV
├── futbol/
│   ├── README.md              este archivo
│   ├── modelo/                fuerza de equipo (Dixon-Coles + xG), simulación minuto a minuto, jugadores
│   ├── datos/                 descargadores por fuente (football-data, understat, alineaciones, árbitros, clima)
│   ├── serie_a/
│   │   ├── raw/<fecha>/       datos crudos con fecha
│   │   ├── partidos/          un JSON de entrada por partido (como games/ en NBA)
│   │   ├── jornadas/          una por jornada (como slates/)
│   │   └── resultados/        resultados reales y evaluación
│   ├── premier/  laliga/  champions/  europa/   (misma estructura, más adelante)
│   └── build_site_futbol.py   escribe docs/futbol/<liga>/data/
└── docs/                      la web
    ├── index.html             PORTADA: elegir deporte y liga (NBA, Serie A, Premier, LaLiga, Champions, Europa)
    ├── nba/                   la web NBA actual (cuando se mueva, ver 7.3)
    ├── futbol/
    │   ├── serie-a/index.html + data/
    │   ├── premier/  laliga/  champions/  europa/
    ├── assets/                estilos y JS comunes (tema claro/oscuro, Mis picks, Mi combinada)
    ├── manifest.webmanifest  OneSignalSDKWorker.js   (en la raíz: la PWA y los avisos cubren todo el sitio)
```

### 7.3 Plan para la web (sin romper la NBA)

1. **Fase 1**: crear `docs/futbol/serie-a/` como página nueva. La NBA sigue en la raíz. Añadir en la cabecera de
   la NBA un selector de deporte/liga que enlace a Serie A.
2. **Fase 2**: cuando Serie A esté estable, mover la NBA a `docs/nba/` y poner en la raíz la portada. La raíz debe
   redirigir enlaces viejos con hash (`/#mis-picks`, `/#cup`, `#migrar=`) a `/nba/…`. El dominio es el mismo, así
   que `localStorage` (Mis picks `nbap-mine`, tema) se conserva. El service worker de OneSignal y el manifest se
   quedan en la raíz para que la PWA instalada y los avisos sigan funcionando; los avisos llevan etiqueta por
   deporte/liga para que cada usuario elija qué recibir.
3. **Fase 3**: "Mis picks" y "Mi combinada" comunes a todos los deportes (una sola clave de almacenamiento con el
   deporte en cada pick), y combinadas entre deportes.
4. Cuidar el tamaño: hoy `docs/index.html` pesa ~470 KB y `docs/data/index.json` ~3,5 MB. Cada liga debe tener
   sus propios JSON y la portada solo un resumen ligero (picks del día de cada liga).

### 7.4 Formato de un partido de fútbol (propuesta inicial)

```json
{
  "match": {"liga": "serie_a", "temporada": "2026-27", "jornada": 13, "fecha": "2026-11-29",
            "hora_local": "20:45", "hora_bogota": "14:45", "local": "INT", "visitante": "JUV",
            "estadio": "San Siro", "neutral": false, "competicion": "liga", "derbi": true},
  "contexto": {"arbitro": "Nombre", "clima": {"lluvia_mm": 0.0, "viento_kmh": 8},
               "descanso_dias": {"INT": 3, "JUV": 6}, "europa_entre_semana": {"INT": "UCL", "JUV": null},
               "en_juego": {"INT": "titulo", "JUV": "champions"}},
  "alineaciones": {"estado": "probable|oficial", "INT": {"titulares": ["..."], "banco": ["..."]}},
  "bajas": {"INT": [{"jugador": "...", "motivo": "lesion|sancion", "p_juega": 0.0}]},
  "jugadores": {"INT": [{"nombre": "...", "pos": "DC", "p_titular": 0.9, "min90": 0.85,
                          "remates90": 3.1, "xg90": 0.52, "xa90": 0.10, "amarillas90": 0.15,
                          "penaltis": true, "corners": false}]},
  "cuotas": {"casas": [{"casa": "Betano", "region": "CO", "1x2": [2.1, 3.3, 3.6], "total_2.5": [1.95, 1.85],
                         "ambos_marcan": [1.75, 2.0]}]},
  "props": {"...": "líneas y cuotas por jugador y mercado"}
}
```

---

## 8. Hoja de ruta sugerida

| Fase | Entregable | Criterio para pasar a la siguiente |
|---|---|---|
| 0 | Probar fuentes de datos (nube y PC) y anotarlas en memoria. Estructura `futbol/` y `comun/`. | Fuentes estables para resultados, xG, alineaciones y cuotas CO. |
| 1 | Histórico Serie A (≥5 temporadas de football-data + Understat). | Datos limpios con cuotas de cierre. |
| 2 | Modelo de equipo (Dixon-Coles + xG + localía + descanso) y simulación minuto a minuto. Backtest por temporadas. | Log loss en 1X2 y totales cercano o mejor que la cuota de cierre sin margen en la mezcla; empates calibrados. |
| 3 | Props de jugador (titularidad, remates, goles, asistencias, tarjetas) + córners y tarjetas de equipo. | Calibración por rango de probabilidad; % fuera de p10–p90 ~10% por lado. |
| 4 | Página `docs/futbol/serie-a/` con jornada, partido, ficha de jugador, picks y Mis picks. | Revisión de Nicolas. |
| 5 | Rutina de jornada (previa, noche anterior, alineaciones oficiales) con tareas programadas y avisos. | Dos semanas en vivo con evaluación. |
| 6 | Portada multi-deporte y NBA en `/nba/`. | Sin romper la PWA ni Mis picks. |
| 7 | Premier, LaLiga (mismo modelo, parámetros por liga) y Champions/Europa League (fuerza entre ligas con ClubElo). | Backtest por liga. |

**Antes de publicar picks con dinero real**: al menos una temporada de backtest y unas semanas de picks "en
seco" (publicados y evaluados sin recomendarlos), como se debió hacer en NBA.

---

## 9. Dónde mirar en el código NBA

| Tema | Archivo |
|---|---|
| Simulación y parámetros del modelo, con el historial de por qué cambió cada uno | `model.py` (comentarios de cabecera y de cada constante) |
| Mezcla con la casa, filtros, topes, parlays, errores de cuota, web | `build_site.py` |
| Historial de versiones del modelo y sus backtests | `CHANGELOG.md` |
| BD de rankings | `db/README.md`, `db/build_db.py`, `db_link.py` |
| Minutos por rotación reciente | `minutes.py` |
| Evaluación tras la jornada | `evaluate.py`, `backtest_market.py`, `bt_stars.py` |
| Rutina diaria y tareas programadas | `docs/README.md`, `tareas/` |
| Cuotas colombianas | `odds/fetch_co.py`, `odds/compare_books.py` |
| Avisos push | `avisos.py` |
