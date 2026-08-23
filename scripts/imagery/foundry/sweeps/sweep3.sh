#!/bin/zsh
# Sweep 3: paint over the clean base map (OSM vectors + aerial trees/dry), tile control, style ref, three painters.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
for H in 7 2; do
  HH=$(printf "%02d" $H); BASE=cond/hole-$HH-base.png; REF=refs/hole-$HH-original.png; OUT=out/hole$H-basemap
  for B in sdxl juggernaut dreamshaper; do
    echo "[$(date '+%H:%M:%S')] hole $H base-map, painter $B"
    $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base $B --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 0.8 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-basemap
  done
  echo "[$(date '+%H:%M:%S')] hole $H base-map, juggernaut painted prompt + higher strength"
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.9 --controlnet-scale 0.8 0.6 --prompt cinematic --measure --out $OUT --tag=-basemap
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.8 --controlnet-scale 0.8 --prompt painted --measure --out $OUT --tag=-basemap
done
echo "[$(date '+%H:%M:%S')] SWEEP3 DONE"
