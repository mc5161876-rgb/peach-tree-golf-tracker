#!/bin/zsh
# Sweep 2: edge-based control so style can take hold. Waits for sweep 1 and the canny/depth downloads.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
until grep -q "SWEEP DONE" logs/sweep1.log && grep -q "depth ->" logs/dl-canny.log; do sleep 10; done
for H in 7 2; do
  if [ $H = 2 ]; then AER=(--aerial cond/hole-02-aerial-bluewater.png); REF=refs/hole-02-original.png; else AER=(); REF=refs/hole-07-original.png; fi
  OUT=out/hole$H
  echo "[$(date '+%H:%M:%S')] hole $H canny grid"
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control canny --ip-mode style style-layout --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.5 0.7 0.9 --prompt painted --measure --out $OUT
  echo "[$(date '+%H:%M:%S')] hole $H canny prompt variants"
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control canny --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.7 --prompt cinematic --measure --out $OUT
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control canny --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.7 --prompt neutral --measure --out $OUT
  echo "[$(date '+%H:%M:%S')] hole $H tile+canny"
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control tile+canny --ip-mode style style-layout --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.3 --second-scale 0.7 --prompt painted --measure --out $OUT
  echo "[$(date '+%H:%M:%S')] hole $H depth probe + plus adapter"
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control depth --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.7 --prompt painted --measure --out $OUT
  $PY generate_styled_card.py --hole $H $AER --style-ref $REF --control canny --adapter plus-vit-h --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.7 --prompt painted --measure --out $OUT
done
echo "[$(date '+%H:%M:%S')] SWEEP2 DONE"
