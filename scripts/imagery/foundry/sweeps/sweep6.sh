#!/bin/zsh
# Sweep 6: paint realism over the v5 procedural skeleton (tight boundaries) (holes 7 and 2). Lower strength — the look is already in the base.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
until grep -q "SWEEP5 DONE\|Traceback" logs/sweep5.log; do sleep 10; done
for H in 7 2; do
  HH=$(printf "%02d" $H); BASE=cond/hole-$HH-base-v5.png; REF=refs/hole-$HH-original.png; OUT=out/hole$H-v5
  echo "[$(date '+%H:%M:%S')] sweep6 hole $H: juggernaut over v5"
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.55 0.7 0.85 --controlnet-scale 0.8 --prompt photo --measure --out $OUT --tag=-v5
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.7 0.85 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-v5
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.7 --controlnet-scale 0.8 --prompt photo --work-scale 2 --measure --out $OUT --tag=-v5
done
echo "[$(date '+%H:%M:%S')] SWEEP6 DONE"
