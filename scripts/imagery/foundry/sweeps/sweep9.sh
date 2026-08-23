#!/bin/zsh
# Sweep 9: freedom for the painter, outlines from the SKELETON (canny of the skeleton), tile weak. Hole 7.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
BASE=cond/hole-07-base-v6.png; REF=refs/hole-07-original.png; OUT=out/hole7-v6-free
for B in juggernaut dreamshaper; do
  echo "[$(date '+%H:%M:%S')] $B tile0.3+canny0.8 s0.85/0.95"
  $PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base $B --control tile+canny --controlnet-scale 0.3 --second-scale 0.8 --ip-mode style --ip-scale 0.8 --strength 0.85 0.95 --prompt cinematic --measure --out $OUT --tag=-free
done
echo "[$(date '+%H:%M:%S')] juggernaut pure canny(skeleton) 0.9, s0.95"
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --control canny --controlnet-scale 0.9 --ip-mode style --ip-scale 0.8 --strength 0.95 --prompt cinematic --measure --out $OUT --tag=-free
echo "[$(date '+%H:%M:%S')] SWEEP9 DONE"
