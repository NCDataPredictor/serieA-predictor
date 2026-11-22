# Fuentes de datos de fútbol (probadas el 22-nov-2026)

Desde la nube (Claude) todas las webs de fútbol dan 403 del proxy. Desde el PC de Nicolas
(`C:\Users\Usuario 1\Documents\NCDataPredictor`):

| Fuente | Estado | Para qué |
|---|---|---|
| **FotMob** `/api/data/leagues?id=55[&season=2025%2F2026]`, `/api/data/matchDetails?matchId=` | ✅ Principal (`fotmob.py`) | Estadísticas de equipo total y por tiempo (posesión, remates, a puerta, córners, fueras de lugar, amarillas, rojas, faltas, pases, xG), por jugador (minutos, remates, a puerta, faltas cometidas/recibidas, pases precisos), árbitro con promedios (ojo: a veces de la Serie B), eventos con minuto, shotmap (x 0-105, y 0-68, situación, xG), bajas con regreso previsto. La ruta vieja `/api/...` da 404. |
| **365Scores** `webws.365scores.com/web/...` (competitions=17) | ✅ Respaldo (pendiente) | Casi lo mismo; además riesgo de sanción por amarillas. Valores como texto ("49%", "49/52 (94%)"). |
| **ESPN** scoreboard / summary | ✅ (pendiente) | El *commentary* trae córners, fueras de lugar y faltas **con minuto** (FotMob y 365Scores solo por tiempo): mejora la distribución por tramos de esas tres estadísticas. |
| **Fantacalcio** probabili formazioni (HTML) | ✅ (pendiente) | XI probable con % de titularidad, dudas, sancionados, apercibidos. Nombres abreviados: hay que cruzarlos con FotMob. |
| **Transfermarkt** lesionados (HTML) | ✅ | Lesiones. |
| **Open-Meteo** | ✅ | Clima (el de FotMob puede ser el del momento de la consulta). |
| Sofascore | ❌ 403 (protección antibots; no se evade) | |
| football-data.co.uk | ❌ bloqueado por la operadora (Coljuegos) | Sería la base de cuotas de cierre para el backtest: probar con otra red. |
| Understat | ❌ en mantenimiento | |
| FBref | ❌ 403 de Cloudflare | |
| ClubElo | ❌ caído ese día | |

Pendiente de verificar con datos reales: qué lado es y=0 en el shotmap de FotMob (`INVERTIR_Y` en `fotmob.py`;
se comprueba con los remates de un extremo izquierdo conocido) y cómo marca FotMob una alineación probable.
