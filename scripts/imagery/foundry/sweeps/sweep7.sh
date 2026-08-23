#!/bin/zsh
# Sweep 7: paint over the v6 skeleton (better crowns), both holes; one 2x each.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
until grep -q "SWEEP6 DONE\|Traceback" logs/sweep6.log; do sleep 10; done
for H in 7 2; do
  HH=$(printf "%02d" $H); BASE=cond/hole-$HH-base-v6.png; REF=refs/hole-$HH-original.png; OUT=out/hole$H-v6
  echo "[$(date '+%H:%M:%S')] sweep7 hole $H: juggernaut over v6"
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 0.75 --controlnet-scale 0.8 --prompt cinematic --measure --out $OUT --tag=-v6
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 --controlnet-scale 0.8 --prompt photo --measure --out $OUT --tag=-v6
  $PY generate_styled_card.py --hole $H --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 --controlnet-scale 0.8 --prompt cinematic --work-scale 2 --measure --out $OUT --tag=-v6
done
echo "[$(date '+%H:%M:%S')] SWEEP7 DONE"
