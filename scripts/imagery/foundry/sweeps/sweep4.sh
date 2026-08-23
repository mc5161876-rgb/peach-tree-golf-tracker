#!/bin/zsh
# Sweep 4: paint over the v3 base maps (OSM vectors + aerial trees/dry + aerial detail). Tile control pins the base; style ref + stronger painters for the look.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
for H in 7 2; do
  HH=$(printf "%02d" $H); BASE=cond/hole-$HH-base-detail.png; REF=refs/hole-$HH-original.png; OUT=out/hole$H-v3
  echo "[$(date '+%H:%M:%S')] hole $H v3 — juggernaut"
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.8 0.95 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-v3
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.8 0.95 --controlnet-scale 0.8 --prompt painted --measure --out $OUT --tag=-v3
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.65 --prompt cinematic --measure --out $OUT --tag=-v3
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.8 --guidance 7 --prompt cinematic --measure --out $OUT --tag=-v3
  echo "[$(date '+%H:%M:%S')] hole $H v3 — dreamshaper + sdxl"
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base dreamshaper --control tile --ip-mode style --ip-scale 0.8 --strength 0.8 0.95 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-v3
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base sdxl --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-v3
done
echo "[$(date '+%H:%M:%S')] SWEEP4 DONE"
