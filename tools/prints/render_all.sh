#!/bin/sh
# Render every plate at print resolution (A2 at 300 dpi, 4961 x 7016 px).
# Expects the data to be in place: see README.md.
#   sh render_all.sh            # all plates
#   DPI=600 sh render_all.sh    # sharper line plates for A0 (the 3D plates take 4x as long)
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
DPI="${DPI:-300}"
SPP="${SPP:-48}"

$PY kenya_rivers.py "$DPI"
$PY kenya_roads.py "$DPI"
$PY contours.py "$DPI"
$PY population.py kenya "$DPI" "$SPP"
for plate in kenya kenya-forest mount-kenya kilimanjaro rift-valley; do
  $PY relief.py "$plate" "$DPI" "$SPP"
done
