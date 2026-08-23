#!/bin/zsh
# Sweep 5 (hole 7, look iteration): richer base detail, looser tile grip, photo vs cinematic prompts, plus adapter, one 2x card.
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
# let sweep 4 finish hole 7, then take the GPU
until grep -q "hole 2 v3" logs/sweep4.log; do sleep 10; done
pkill -f sweep4.sh || true; sleep 1; pkill -f "generate_styled_card.py --hole 2" || true; sleep 2
echo "[$(date '+%H:%M:%S')] SWEEP4 DONE (hole 7 only; hole 2 skipped for sweep 5)" >> logs/sweep4.log
BASE=cond/hole-07-base-detail16.png; REF=refs/hole-07-original.png; OUT=out/hole7-v4
echo "[$(date '+%H:%M:%S')] sweep5: juggernaut, looser grip, photo vs cinematic"
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.5 0.65 --prompt photo --measure --out $OUT --tag=-d16
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.5 0.65 --prompt cinematic --measure --out $OUT --tag=-d16
echo "[$(date '+%H:%M:%S')] sweep5: plus adapter + 2x"
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --adapter plus-vit-h --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.65 --prompt photo --measure --out $OUT --tag=-d16
$PY generate_styled_card.py --hole 7 --aerial $BASE --style-ref $REF --base juggernaut --control tile --ip-mode style --ip-scale 0.8 --strength 0.95 --controlnet-scale 0.65 --prompt photo --work-scale 2 --measure --out $OUT --tag=-d16
echo "[$(date '+%H:%M:%S')] SWEEP5 DONE"
