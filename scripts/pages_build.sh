#!/usr/bin/env bash
# Build de Cloudflare Pages para ncdatapredictor.pages.dev (comando de build del proyecto; carpeta de salida: docs).
# La NBA vive en su propio repo (NCDataPredictor/nba-predictor, público): se trae su web en cada build y se sirve en /nba/.
# El repo NBA llama al deploy hook de este proyecto en cada push a main, así /nba/ se actualiza solo.
set -euo pipefail
tmp=$(mktemp -d)
git clone --depth 1 --branch "${NBA_BRANCH:-main}" https://github.com/NCDataPredictor/nba-predictor.git "$tmp/nba"
rm -rf docs/nba
cp -r "$tmp/nba/docs" docs/nba
rm -f docs/nba/CNAME
echo "NBA copiada en docs/nba ($(du -sh docs/nba | cut -f1))"
# La Champions vive en NCDataPredictor/champions-league-predictor (público): se trae su web y se sirve en /champions/.
# Si el clon falla no se cae el build de todo el sitio: /champions/ queda sin publicar en ese build.
if git clone --depth 1 --branch "${UCL_BRANCH:-main}" https://github.com/NCDataPredictor/champions-league-predictor.git "$tmp/ucl"; then
  rm -rf docs/champions
  cp -r "$tmp/ucl/docs/champions" docs/champions
  echo "Champions copiada en docs/champions ($(du -sh docs/champions | cut -f1))"
else
  echo "No se pudo clonar la Champions: /champions/ no se publica en este build"
fi
