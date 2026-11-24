#!/usr/bin/env bash
# Clona ppi--datos en ./datos sin traer la cinta entera (1,2 GB): todo el repositorio salvo tiempo_real/, y de tiempo_real/
# solo las fechas pedidas. Uso: clonar_datos.sh <ultima|todo|AAAA-MM-DD ...>. Necesita DATOS_TOKEN.
# (24/11/2026: los trabajos sobre la cinta corren en ppi-lector, sin gastar minutos, y guardan en ppi--datos)
set -euo pipefail
git clone -q --depth 1 --filter=blob:none --no-checkout "https://x-access-token:${DATOS_TOKEN}@github.com/Dcostanzo30/ppi--datos.git" datos
cd datos
todas=$(git ls-tree --name-only HEAD tiempo_real/ | sed 's#tiempo_real/##' | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort)
case "${1:-ultima}" in
  ""|ultima) fechas=$(echo "$todas" | tail -1) ;;
  todo) fechas="$todas" ;;
  *) fechas="$*" ;;
esac
git sparse-checkout init --no-cone
{ echo '/*'; echo '!/tiempo_real/'; echo '!/tiempo_real_afuera/'; for f in $fechas; do echo "/tiempo_real/$f/"; done; } > .git/info/sparse-checkout
git checkout -q main
echo "lector/" >> .git/info/exclude
echo "fechas de la cinta: $(echo $fechas | wc -w) ($(echo $fechas | tr ' ' '\n' | head -1) .. $(echo $fechas | tr ' ' '\n' | tail -1))"
echo "FECHAS_CINTA=$(echo $fechas | tr '\n' ' ')" >> "${GITHUB_ENV:-/dev/null}"
git config user.email "bot@users.noreply.github.com"
