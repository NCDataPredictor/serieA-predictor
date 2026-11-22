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
