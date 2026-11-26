# Premier League Predictor · instrucciones para crearla

Guía para el agente que construya la web de **Premier League** de NCData Predictor con las mismas características
y el mismo funcionamiento que NBA, Serie A y Champions. Escrita el 26-nov-2026 a partir de los repos
`NCDataPredictor/nba-predictor`, `NCDataPredictor/serieA-predictor` y `NCDataPredictor/champions-league-predictor`.

Lee antes, en este orden:
1. [`futbol/CONTEXTO.md`](CONTEXTO.md): cómo se hizo la NBA, sus lecciones y el plan de fútbol (obligatorio).
2. [`README.md`](../README.md) de este repo: el flujo y el modelo de fútbol (`futbol-0.1`).
3. [`futbol/datos/FORMATO.md`](datos/FORMATO.md) y [`futbol/datos/FUENTES.md`](datos/FUENTES.md).

Lo que esta guía **no** cambia: el modelo de fútbol es el mismo; la Premier solo cambia la configuración de liga,
los nombres de equipos y, cuando haya backtest, sus parámetros. Un cambio de modelo se revisa con Nicolas antes de
mergear (regla del 20-nov); datos, web y scripts se mergean solos por PR con squash.

---

## 1. Decisión de arquitectura: repo propio, servido en `/premier/`

Igual que la Champions, la Premier vive en **su propio repo** y el sitio central la copia en cada build:

| Pieza | Dónde |
|---|---|
| Repo nuevo | `NCDataPredictor/premier-league-predictor` (**público**, porque `scripts/pages_build.sh` lo clona sin credenciales) |
| Web | `docs/premier/` del repo nuevo (index.html, manual/, data/, icons/, logos/) |
| URL pública | `https://ncdatapredictor.pages.dev/premier/` |
| Portada y PWA | siguen en `serieA-predictor/docs/` (portada `docs/index.html`, `manifest.webmanifest`, `OneSignalSDKWorker.js` en la raíz) |

Por qué repo propio: las acciones programadas de cada liga empujan a `main` varias veces al día; separadas no se
pisan, cada liga tiene su `concurrency` y un fallo en una no tumba las otras. La NBA y la Champions ya funcionan así.

**Base de código**: partir del repo de la **Champions** (es el más nuevo: soñadora, props de The Odds API, props
de Betano, recuento con soñadoras, apertura de picks, deploy hook) y **devolver la fuerza de equipo al modo de
Serie A** (Dixon-Coles con el histórico propio de la liga), porque la Premier, como la Serie A, es una liga
doméstica con 38 jornadas y rivales comunes. Lo específico de la Champions se quita (ver §3.3).

---

## 2. Pasos en orden (lista de comprobación)

1. **Crear el repo** `NCDataPredictor/premier-league-predictor` (público, rama `main`). Lo crea Nicolas desde la
   cuenta de la organización o con el permiso de la sesión; añadirlo al proyecto de Claude.
2. **Copiar** el contenido del repo de la Champions (sin `futbol/champions/`, `docs/champions/` ni el historial).
3. **Renombrar y configurar** la liga (§3): `premier` en Python, `premier` en la web.
4. **Equipos**: `futbol/datos/equipos_epl.py` con los 20 equipos y sus alias (§4).
5. **Fuentes**: comprobar los IDs de FotMob, Kambi y The Odds API desde la nube y desde el PC (§5) y anotarlos en
   `FUENTES.md` y en la memoria del proyecto.
6. **Histórico**: `python -m futbol.datos.fotmob historico` desde el PC (temporada actual + anterior).
7. **Backtest** (`python -m futbol.backtest premier`) antes de publicar picks: log loss frente a la casa,
   calibración, empates y % fuera de p10–p90 (§6.4).
8. **Web** `docs/premier/` (§7), manual (§7.4), íconos y logo (§9).
9. **Acciones** `jornada.yml`, `recuento.yml`, `avisos.yml`, `ncdata.yml` (§8) y secretos.
10. **Sitio central** (PR en `serieA-predictor`): `pages_build.sh`, portada `MODELOS`, `manifest`, logo (§9).
11. **Selector de modelos** en NBA, Serie A y Champions: pasar la Premier de "Próximamente" a enlace (§9.3).
12. Unas semanas de **picks en seco** y luego en vivo; memoria del proyecto al día.

---

## 3. Estructura del repo y qué cambiar

```
premier-league-predictor/
├── .claude/agents/ux-disenador.md        copiar y cambiar rutas a docs/premier/
├── .github/workflows/
│   ├── jornada.yml                       cada 3 h + horas de alineaciones (§8)
│   ├── recuento.yml                      22:30 Bogotá: resultados y liquidación de picks
│   ├── avisos.yml                        avisos al celular al cambiar docs/premier/data/index.json
│   └── ncdata.yml                        cada push a main pide el redespliegue del sitio central
├── .gitignore                            igual (futbol/*/raw/, ejemplos, .venv/)
├── README.md                             flujo y modelo, adaptado a la Premier
├── comun/mercado.py                      igual (mezcla con la casa, EV, quitar margen)
├── futbol/
│   ├── CONTEXTO.md                       copia del de Serie A
│   ├── build_site_futbol.py              LIGAS = {"premier": ...}
│   ├── backtest.py  recuento.py  sonador.py  avisos_futbol.py
│   ├── datos/  (fotmob, kambi, betano, betano_props, oddsapi, oddsapi_props, equipos_epl, FORMATO, FUENTES)
│   ├── modelo/ (params, base, fuerza, contexto, jugadores, simular, mercados; sin fuerza_mercado)
│   └── premier/
│       ├── historico/      fotmob_2025-26.json, fotmob_2026-27.json (normalizado, se sube)
│       ├── partidos/       <fecha>-<LOC>-<VIS>.json, uno por partido a predecir
│       ├── cuotas/         Kambi / Betano por partido (+ betano_props.json)
│       ├── consenso/       fotos de The Odds API por fecha
│       ├── recuento/       picks.json, sonador.json (acumulados)
│       ├── backtest/       resumen.json, filas.json
│       ├── nube/           estado.json, props_estado.json (qué funcionó en la última corrida)
│       └── raw/            crudos de FotMob (NO se suben; caché de Actions)
└── docs/
    ├── push.json           {"onesignal_app_id": "8156f999-…", "site": "https://ncdatapredictor.pages.dev/"} (el mismo)
    └── premier/
        ├── index.html      la web (un solo archivo HTML+CSS+JS)
        ├── manual/index.html
        ├── icons/icon-192.png  icon-512.png
        ├── logos/premier.png
        └── data/           index.json, <id>.json, equipos.json, recuento.json, resultados.json
```

### 3.1 Configuración de liga (buscar `champions` y `serie_a` en todo el código)

| Archivo | Cambio |
|---|---|
| `futbol/build_site_futbol.py` | `LIGAS = {"premier": {"web": "premier", "nombre": "Premier League", "temporada": "2026-27", "anterior": "2025-26"}}` |
| `futbol/datos/fotmob.py` | `LIGA_ID = 47` (Premier en FotMob, **verificar**), `DIR_LIGA = futbol/premier`, `"liga": "premier"` en los partidos, web `docs/premier/data`. Volver al flujo de Serie A: `historico` (temporada actual + anterior de la liga) y `proximos`; el modo `equipos` de la Champions sobra. Comprobar `INVERTIR_Y` con un extremo izquierdo conocido, como en Serie A. |
| `futbol/datos/kambi.py` | `LIGAS = {"premier": "football/england/premier_league"}` (**verificar** en el árbol de grupos de Kambi), `default="premier"`. Quitar `_ruta_champions` o generalizarla. |
| `futbol/datos/oddsapi.py` y `oddsapi_props.py` | `SPORT = {"premier": "soccer_epl"}`; rutas a `futbol/premier/`. Ver si las casas "uk"/"eu" ofrecen props de remates en EPL (en Champions las "eu" no los daban). |
| `futbol/datos/betano.py`, `betano_props.py` | Nombres de Betano CO → código (via `equipos_epl`), rutas `futbol/premier/`. |
| `futbol/recuento.py` | `WEB = {"premier": "premier"}`, default `premier`. |
| `futbol/avisos_futbol.py` | `LIGAS = {"premier": {"tag": "premier", "nombre": "Premier League", "emoji": "⚽"}}` (o 🦁), textos de prueba y URL `premier/`. |
| `futbol/backtest.py` | `choices` de liga (sale de `B.LIGAS`). |
| `futbol/sonador.py` | Solo el docstring; las reglas se quedan (§6.3). |
| Workflows | `futbol/premier`, `docs/premier`, `concurrency: jornada-premier`, nombre "Jornada Premier (nube)". |

### 3.2 Parámetros (`futbol/modelo/params.py`)

Empezar con los de Serie A y **solo cambiar con backtest**. Diferencias esperadas a medir (no a poner a ojo):
- `LOCALIA_GOLES`: en Premier la localía es parecida o algo menor que en Serie A.
- `ROJA_DIRECTA_POR_FALTA`, `AMARILLA_SIN_FALTA`: la Premier saca menos tarjetas que la Serie A (≈3,5–4 por
  partido frente a ≈4,5–5) y pita menos faltas; si el histórico lo confirma, ajustar.
- `DERBI_*`: lista de derbis propia (§4).
- `MARGEN_UN_LADO`, `PESO_COMPETICION`, `ANCLA_*`: son de la Champions. `MARGEN_UN_LADO` se puede dejar (escaleras
  N+ de Betano); `ANCLA_MERCADO`/`ANCLA_LIMITES`/`PESO_COMPETICION` se quitan.

### 3.3 Qué quitar de la base Champions

- `futbol/modelo/fuerza_mercado.py`, `lambda_mercado` y `_anclar_al_mercado` en `build_site_futbol.predecir`: la
  Premier usa `fuerza.py` (Dixon-Coles, vida media 180 días, 0,6·xG + 0,4·goles, localía encogida, ρ) como Serie A.
- La columna `ucl` y la mezcla de competiciones en las tasas de jugador (`_recientes_jugadores`).
- `equipos_ucl.py` → `equipos_epl.py`.
- Cualquier texto "Champions", "fase liga", "36 equipos" en la web y el manual.

### 3.4 Ascendidos y prior entre temporadas

`build_site_futbol.predecir` ya detecta ascendidos (equipos de esta temporada que no estaban en la anterior) y
`fuerza.ajustar` les pone un prior por debajo de la media. En 2026-27 hay 3 ascendidos de la Championship:
comprobar que el histórico de la temporada anterior está completo para que salgan solos, o pasarlos en
`partido["ascendidos"]`.

---

## 4. Equipos (`futbol/datos/equipos_epl.py`)

- 20 equipos con un **código de 3 letras** igual en FotMob, Kambi, Betano, The Odds API y la web (`ARS`, `AVL`,
  `BOU`, `BRE`, `BHA`, `CHE`, `CRY`, `EVE`, `FUL`, `LIV`, `MCI`, `MUN`, `NEW`, `NFO`, `TOT`, `WHU`, `WOL`…, más los
  ascendidos de 2026-27). Ojo con choques: Manchester City/United, Nottingham/Newcastle, Wolves/West Ham.
- Alias por fuente: nombre en inglés de Kambi y The Odds API ("Man City", "Spurs", "Nott'm Forest", "Brighton &
  Hove Albion"), nombre en español de Betano CO ("Manchester City", "Tottenham", "Nottingham Forest"…).
- Usar la misma clase `Nombres()`/`codigo()` que `equipos_ucl.py` (normaliza tildes, "FC", "AFC", "&").
- **Derbis** (para `derbi: true`): Manchester (MCI–MUN), Merseyside (LIV–EVE), North London (ARS–TOT), los de
  Londres (CHE, ARS, TOT, WHU, CRY, FUL, BRE), Tyne-Wear si hay ascendido, East Midlands, Liverpool–Man United.
- `docs/premier/data/equipos.json`: escudos y colores (el de Champions sale de `fotmob equipos`; aquí se arma igual
  con los IDs de FotMob de los 20 equipos).

---

## 5. Fuentes de datos (repetir la prueba de Serie A)

Desde la nube de Claude las webs de fútbol daban 403 el 22-nov, pero las **acciones de GitHub** sí leen FotMob, Kambi
y The Odds API en Serie A y Champions (`nube/estado.json` del 26-nov: todo `success`; Kambi falló en una corrida
de la Champions). Probar cada una desde **Actions**, la **nube de Claude** y el **PC de
Nicolas** (`C:\Users\Usuario 1\Documents\NCDataPredictor`) y anotarlo.

| Necesidad | Fuente | Notas para la Premier |
|---|---|---|
| Histórico y próxima jornada | FotMob `/api/data/leagues?id=47[&season=2025%2F2026]`, `/api/data/matchDetails?matchId=` | Mismo normalizador. Comprobar que el árbitro trae promedios de Premier (`leagueId == 47`). |
| Cuotas de equipo | Kambi (Unibet, Rushbet, BetPlay) | Se lee desde Actions. Mercados ya mapeados en `kambi.MERCADOS`. |
| Cuotas Betano CO | Navegador del PC de Nicolas, `EXTRACTOR_JS` de `betano.py` y `betano_props.py` (solo lectura) | Betano bloquea la nube; si hay extracto de Betano, se respeta por encima de Kambi. |
| Consenso y props | The Odds API (`soccer_epl`), secreto `ODDS_API_KEY` | Plan gratuito: cuota mensual limitada; `MIN_HORAS` limita a 2 consultas/día por liga. Repartir con Serie A y Champions (la misma clave). |
| Alineaciones probables | FotMob (si marca "probable"), Fantasy Premier League (`fantasy.premierleague.com/api/bootstrap-static/`: estado de lesión y % de jugar), RotoWire, Sports Mole | FPL es oficial y gratis: **probarla primero**; trae `chance_of_playing_next_round` y noticias. |
| Alineación oficial | FotMob (~60 min antes) | |
| Lesiones y sanciones | FotMob (bajas con regreso), FPL, Transfermarkt | En Premier: 5 amarillas antes de la jornada 19 = 1 partido; 10 antes de la 32 = 2. Verificar el reglamento 2026-27. |
| Árbitros | FotMob; designaciones de la PGMOL ~5 días antes | |
| Clima | Open-Meteo | Por coordenadas del estadio. |

Guardar lo crudo en `futbol/premier/raw/` (caché de Actions, no en git).

---

## 6. Modelo, simulación y mercados

### 6.1 Modelo (igual que Serie A)

`base.py` (BD de contexto), `fuerza.py` (Dixon-Coles), `contexto.py` (liga × ataque × defensa × localía × árbitro
× derbi × H2H × cruce de estilos), `jugadores.py` (titularidad, salida/entrada, tasas por 90, bajas con heredero y
efecto con/sin), `simular.py` (Monte Carlo **minuto a minuto, 20.000 sims, semilla fija**: marcador, rojas,
tramos de 15', estadísticas por jugador, suplente de oro), `mercados.py`. Versión `futbol-0.1`; si la Premier
necesita parámetros distintos, versionarlos (`MODEL_VERSION`) y separar unidades por versión en la web.

### 6.2 Mercados que salen de cada partido

- **Partido**: 1X2, doble oportunidad, descanso, descanso/final, total de goles, ambos marcan, marcadores exactos,
  primer gol, por tramo.
- **Líneas de equipo** (selector `#linea-st`, `STATS_EQ`): **goles por equipo y total** (añadido el 25/26-nov en
  serieA #8 y champions #17: el modelo ya simulaba `mercados.equipo[...]["goles"]`, la web solo lo mostraba),
  remates, remates a puerta, córners, faltas, amarillas, rojas, fueras de lugar, pases. Cada línea con "Últimos"
  (historial) y botón **+** a Mi combinada. En la Premier vienen incluidos desde el primer día: solo hay que
  conservar `"goles"` al principio de `STATS_EQ`.
- **Jugadores**: remates, remates a puerta, faltas cometidas/recibidas, pases, tarjetas, goles y asistencias si la
  casa los ofrece; con y sin **suplente de oro** (si la casa lo ofrece en esa línea, la prob. es titular +
  reemplazo). Atajadas del portero desde The Odds API (`player_goalkeeper_saves`).

### 6.3 Picks, errores de cuota y soñadora

- **Picks** (`build_site_futbol.picks`): solo líneas con cuota real (dos lados, o un lado con `MARGEN_UN_LADO`),
  mezcla con la casa `MKT_W = 0,20`, EV ≥ 3 %, prob. ≥ 50 %, máx. 2 por jugador y 12 por jornada. Nunca se inventa
  una cuota; cuotas decimales.
- **Errores de cuota**: `_candidato_equipo` (historial de la línea ≥ 6 partidos, % de acierto alto, casa ≤ 45 %,
  modelo ≥ 50 %). Mismo umbral.
- **Apertura de picks** (`apertura_picks`): la Champions publica desde las **6:00 Bogotá del día anterior** al
  primer partido de la jornada (pedido del 26-nov, PR champions #18); la Serie A, desde las 19:00 de la víspera
  (`HORA_PICKS`). Para la Premier usar la regla de la Champions (`HORA_PUBLICAR_UTC = 11`) salvo que Nicolas diga
  otra cosa. Antes de esa hora el partido sale con probabilidades, sin picks, sin líneas de casa y sin soñadora.
- **Soñadora** (`futbol/sonador.py`): una combinada por día de partidos, cuota total 50–200, patas con p ≥ 60 % y
  cuota 1,15–3,0, máx. 2 patas por partido (una de equipo y otra de jugador), props solo de jugadores con
  titularidad ≥ 75 %, como mucho la mitad a "Menos de", máx. 20 patas. **Congelada** al empezar el primer partido
  del día; nunca se reemplaza una ya publicada. Récord en Rendimiento con las 5 últimas jornadas visibles
  (`DREAM_PAST_MAX`) y todas en el total. Un partido empezado queda congelado (lo publicado es lo que se evalúa).

### 6.4 Antes de publicar picks con dinero

1. Histórico de 2025-26 y 2026-27 completo.
2. `python -m futbol.backtest premier --desde 4`: log loss en 1X2 y totales frente a la casa sin margen,
   calibración por rango, empates simulados frente a reales, % fuera de p10–p90 (~10 % por lado).
3. Unas semanas de picks "en seco" (publicados y evaluados, marcados como tal) y revisión con Nicolas.

---

## 7. La web `docs/premier/`

### 7.1 Partir de `docs/champions/index.html`

Copiar el archivo y cambiar: título, `<meta>`, colores de la liga (Premier: morado `#38003c`, `#5b0a63`, acento
verde `#00ff85`; ya son los de la tarjeta "Próximamente"), logo, textos, rutas de datos (`data/index.json`,
`data/<id>.json`), tag de avisos (`premier`) y la entrada `cur: true` de `MODELOS_NAV`. Usar el agente
`ux-disenador` para revisar móvil/escritorio y claro/oscuro.

### 7.2 Lo que debe tener (igual que las otras tres)

- **Barra de la jornada**: solo la jornada actual (con sus atrasados); las jugadas aparte tras un separador, con
  marcador final.
- **Portada de la liga**: picks con valor primero (mayor EV), **errores de cuota**, pick del día, soñadora.
- **Panel de cada partido** con pestañas: Resumen, Contexto (árbitro, H2H, forma, descanso, clima), Distribución
  (goles, marcadores, tramos de 15'), **Líneas de equipo** (con goles), Jugadores (ficha con historial `#jug-dlg`,
  suplente de oro), Bajas.
- **Rendimiento** (`#rendimiento`): unidades y ROI de los picks liquidados (`data/recuento.json`) y récord de cada
  soñadora.
- **Mis picks** (`#mis-picks`, botón "Lo tomo", guardado en el navegador) y **Mi combinada** (pill flotante,
  stake, cuota total). Claves de almacenamiento propias con prefijo `epl-` (`epl-mine`, `epl-combi`, `epl-combis`, `epl-filtros`, `epl-orden`, `epl-plg-`), como la Champions usa `ucl-…`: no reutilizar las de otra liga.
- **Avisos** (`#avisos-box`): suscripción OneSignal con tag `premier = 1`; el worker está en la raíz del sitio.
- **Selector de modelos** (`#modelos-btn` / `#modelos-dlg`) y tema claro/oscuro (`ncdp-theme`, compartido).
- Franja amarilla si los datos son de ejemplo (`"ejemplo": true`).
- Horas en **Bogotá**. La Premier juega en hora del Reino Unido: Bogotá = UK − 5 h en invierno (GMT) y − 6 h con
  el horario de verano británico (finales de marzo a finales de octubre). Partidos típicos: 7:30, 10:00, 12:30 y
  15:00 Bogotá en invierno.

### 7.3 Datos que lee la web (los genera `build_site_futbol`; no editarlos a mano)

`data/index.json` (resumen ligero que lee también la portada: `partidos[].jornada`, `n_picks`, `n_errores`,
`sonador`, `version`), `data/<id>.json` (todo el partido), `equipos.json`, `recuento.json`, `resultados.json`.

### 7.4 Manual

`docs/premier/manual/index.html`: copiar el de la Champions y adaptar (qué es cada pestaña, cómo leer
probabilidad, cuota justa, EV, suplente de oro, soñadora, cuándo salen los picks).

---

## 8. Tareas programadas (GitHub Actions del repo nuevo)

| Acción | Cuándo | Qué hace |
|---|---|---|
| `jornada.yml` | `15 */3 * * *` (cada 3 h) + horas de alineaciones de los días de partido (≈55 min antes de los saques: p. ej. `35 11,14,16,19 * * 6,0` en invierno, ajustar al calendario y al cambio de hora) | FotMob `historico` y `proximos` → Kambi → The Odds API (consenso y props) → `build_site_futbol premier --solo-futuros` → commit y push a `main` → **deploy hook** → avisos. Deja `futbol/premier/nube/estado.json`. Cada paso con `continue-on-error`. |
| `recuento.yml` | `30 3 * * *` (22:30 Bogotá) | Resultados del día (FotMob) → `python -m futbol.recuento premier` → push → deploy hook. |
| `avisos.yml` | push que cambie `docs/*/data/index.json` y a mano | `python -m futbol.avisos_futbol` (jornada lista, alineaciones confirmadas); "Run workflow" manda un aviso de prueba. |
| `ncdata.yml` | push a `main` en `docs/**` | Llama al deploy hook del sitio central. |

Notas que ya costaron errores:
- Los push hechos con el token de Actions **no disparan otras acciones**: por eso `jornada.yml` y `recuento.yml`
  llaman ellos mismos al hook y a los avisos.
- `git pull --rebase -X theirs origin main` antes del push (gana la corrida más nueva) y `concurrency` común
  (`jornada-premier`) entre jornada y recuento.
- `permissions: contents: write`.
- Si falta el secreto del hook el paso sale **en verde** ("Sin CF_DEPLOY_HOOK_NCDATA"): leer el log, no el color.
- GitHub Actions estuvo bloqueado por facturación el 15-nov en la NBA: si las acciones no corren, revisar eso
  primero.

**Secretos** (mejor a nivel de la organización NCDataPredictor, como ya está `CF_DEPLOY_HOOK_NCDATA`):
`CF_DEPLOY_HOOK_NCDATA`, `ONESIGNAL_REST_API_KEY`, `ODDS_API_KEY`. Comprobar que la organización los comparte con
el repo nuevo (visibilidad "todos los repos" o añadirlo a la lista).

---

## 9. Sitio central, portada, PWA y logos (PR en `serieA-predictor`)

### 9.1 Build de Cloudflare (`scripts/pages_build.sh`)

Añadir, después del bloque de la Champions y con el mismo patrón tolerante a fallos:

```bash
if git clone --depth 1 --branch "${EPL_BRANCH:-main}" https://github.com/NCDataPredictor/premier-league-predictor.git "$tmp/epl"; then
  rm -rf docs/premier
  cp -r "$tmp/epl/docs/premier" docs/premier
  echo "Premier copiada en docs/premier ($(du -sh docs/premier | cut -f1))"
else
  echo "No se pudo clonar la Premier: /premier/ no se publica en este build"
fi
```

Y añadir `docs/premier/` al `.gitignore` de `serieA-predictor` (como `docs/nba/`). El proyecto de Cloudflare
Pages es `ncdatapredictor` (comando de build `bash scripts/pages_build.sh`, salida `docs`); no hace falta un
proyecto nuevo.

### 9.2 Portada (`docs/index.html`) y PWA

- En `MODELOS`, la entrada `premier` pasa de `pronto: true` a:
  `{id: "premier", deporte: "Fútbol · Inglaterra", nombre: "Premier League", texto: "…", url: "premier/",
  datos: "premier/data/index.json", logo: "logos/premier.png", c1: "#38003c", c2: "#5b0a63", stripe: "#00ff85", ink: "#fff"}`
  (añadir `inv: true` si el logo es oscuro). La tarjeta muestra sola "Jornada N · X partidos · Y picks".
- `manifest.webmanifest`: atajo `{"name": "Premier League", "url": "/premier/"}` y actualizar `description`.
- `docs/_redirects`: no hace falta nada salvo que se quiera `/epl → /premier/`.

### 9.3 Selector de modelos en las otras webs

Cambiar la entrada "Premier League" de `MODELOS_NAV` (quitar `pronto: true`, poner `url: "../premier/"` y
`lg: "/logos/premier.png"`) en:
- `serieA-predictor/docs/serie-a/index.html`
- `champions-league-predictor/docs/champions/index.html`
- `nba-predictor/docs/index.html` (allí `lg: "../logos/premier.png"`)

Son tres PRs (uno por repo); la NBA se mergea sola, Serie A y Champions también salvo que Nicolas pida revisarlos.

### 9.4 Logos e íconos

- Logo de la liga: FotMob `https://images.fotmob.com/image_resources/logo/leaguelogo/47.png` (**verificar** el ID).
  Desde la nube `images.fotmob.com` no abre: bajarlo con el **navegador integrado del PC de Nicolas** (abrir la URL
  de la imagen, `fetch(location.href)` → base64) y **verificar con hash por trozos** (al copiar base64 a mano se
  cuelan errores). Guardar en `serieA-predictor/docs/logos/premier.png` (portada y selectores) y en
  `premier-league-predictor/docs/premier/logos/premier.png` (la web de la liga).
- Íconos `docs/premier/icons/icon-192.png` e `icon-512.png` (los usan los avisos: `avisos_futbol` manda
  `site + "premier/icons/icon-192.png"`).
- Escudos de los 20 equipos: los sirve FotMob por ID de equipo en `equipos.json`; la web cae al código de 3 letras si
  no cargan.

---

## 10. Rutina operativa (hora de Bogotá)

1. **Día anterior al primer partido, 6:00** (corrida de las 11:15 UTC): salen picks, líneas de casa y soñadora.
2. **Cada 3 h** durante la jornada (vie–lun; martes/miércoles si hay jornada entre semana; Boxing Day y fin de año
   con jornadas seguidas): datos, cuotas, re-simulación de lo que no ha empezado.
3. **≈55 min antes de cada franja de partidos**: alineaciones oficiales → re-simular → aviso si cambian picks.
4. **22:30**: recuento y Rendimiento.
5. Calendario a vigilar: copas inglesas (FA Cup, EFL Cup) y europeas entre semana (rotaciones), parones FIFA,
   Boxing Day (partidos cada 2–3 días).

---

## 11. Al terminar

- Memoria del proyecto: un archivo `premier-*.md` con repo, URL, IDs verificados (FotMob, Kambi, The Odds API),
  qué fuentes funcionan desde Actions/nube/PC y los PRs; enlazarlo desde `MEMORY.md` y desde `futbol-project`.
- Actualizar `futbol/CONTEXTO.md` (§7) y este archivo si algo cambió en el camino.
- Tras cada merge a `main`: mirar el run de `ncdata.yml` y que `https://ncdatapredictor.pages.dev/premier/data/index.json`
  responda 200.
