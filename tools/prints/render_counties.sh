#!/bin/sh
# Render every county as a relief plate. Counties that already have a
# master at print resolution are skipped unless FORCE=1.
#   sh render_counties.sh               # previews at 150 dpi, for the shop
#   DPI=300 sh render_counties.sh       # print resolution, about 5 minutes each
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
DPI="${DPI:-150}"
SPP="${SPP:-32}"
OUT="${ZP_OUT:-out}"
$PY - <<'PYEOF' > /tmp/zp_counties.txt
from relief import COUNTY_NUMBERS
for name in sorted(COUNTY_NUMBERS, key=COUNTY_NUMBERS.get):
    print(name)
PYEOF
while IFS= read -r name; do
  slug="county-$(echo "$name" | tr 'A-Z ' 'a-z-' | tr -d "'")"
  if [ -z "$FORCE" ] && [ -f "$OUT/$slug.png" ]; then
    echo "skip $slug (print master exists)"; continue
  fi
  $PY relief.py "county:$name" "$DPI" "$SPP"
done < /tmp/zp_counties.txt
