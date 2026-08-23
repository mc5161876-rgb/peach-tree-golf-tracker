#!/bin/zsh
# Sweep 8 (hole 7, 2x, v6 skeleton): more look options while Mario decides — stronger style capture + the yardage-book prompt.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
BASE=cond/hole-07-base-v6.png; REF=refs/hole-07-original.png; OUT=out/hole7-v6
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --adapter plus-vit-h --control tile --ip-mode style --ip-scale 1.0 --strength 0.6 --controlnet-scale 0.8 --prompt cinematic --work-scale 2 --measure --out $OUT --tag=-v6
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 --controlnet-scale 0.8 --prompt painted --work-scale 2 --measure --out $OUT --tag=-v6
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base dreamshaper --control tile --ip-mode style --ip-scale 0.8 --strength 0.6 --controlnet-scale 0.8 --prompt cinematic --work-scale 2 --measure --out $OUT --tag=-v6
echo "[$(date '+%H:%M:%S')] SWEEP8 DONE"
