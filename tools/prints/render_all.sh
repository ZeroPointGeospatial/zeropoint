#!/bin/sh
# Render every plate at print resolution: A2 at 300 dpi with 3 mm bleed
# (5031 x 7086 px), and the city prints at 6744 x 8540 px.
# Expects the data to be in place: see README.md.
#   sh render_all.sh            # everything
#   DPI=600 sh render_all.sh    # sharper line plates for A0 (the 3D plates take 4x as long)
# A 3D plate that has already been rendered at this size is reused from the
# cache; set ZP_FRESH=1 to render it again.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
DPI="${DPI:-300}"
SPP="${SPP:-40}"

# line plates: seconds each
$PY kenya_rivers.py "$DPI"
$PY kenya_roads.py "$DPI"
$PY counties.py "$DPI"
$PY contours.py longonot "$DPI"
$PY contours.py mount-kenya-summit "$DPI"
for city in mombasa kisumu nakuru eldoret; do
  $PY cities.py "$city"
done

# ray-traced plates: about ten minutes each on four cores
$PY population.py kenya "$DPI" "$SPP"
for plate in kenya kenya-forest mount-kenya kilimanjaro rift-valley east-africa \
             county:Kiambu county:Nakuru county:Nyeri county:Kajiado; do
  $PY relief.py "$plate" "$DPI" "$SPP"
done

# the Africa series (plates 20 and 21), from their map specs
$PY relief.py spec:maps/africa-relief.yml "$DPI" "$SPP"
$PY population.py spec:maps/africa-population.yml "$DPI" "$SPP"

# The other 43 county plates are made to order: render_counties.sh.
