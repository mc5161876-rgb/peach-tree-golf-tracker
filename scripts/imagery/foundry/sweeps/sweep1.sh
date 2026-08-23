#!/bin/zsh
set -e
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache PYTORCH_ENABLE_MPS_FALLBACK=1
PY=.venv/bin/python
GRID=(--ip-mode style style-layout full --ip-scale 0.6 1.0 --strength 0.75 0.95 --controlnet-scale 0.8 --prompt painted --measure)
echo "[$(date '+%H:%M:%S')] hole 7 grid"
$PY generate_styled_card.py --hole 7 --style-ref refs/hole-07-original.png $GRID --out out/hole7
echo "[$(date '+%H:%M:%S')] hole 2 grid (bluewater conditioning, drift vs true aerial)"
$PY generate_styled_card.py --hole 2 --aerial cond/hole-02-aerial-bluewater.png --style-ref refs/hole-02-original.png $GRID --out out/hole2
echo "[$(date '+%H:%M:%S')] cross-reference checks (does the ref's layout leak?)"
$PY generate_styled_card.py --hole 7 --style-ref refs/hole-02-original.png refs/hole-06-original.png --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.8 --prompt painted --measure --out out/hole7
$PY generate_styled_card.py --hole 2 --aerial cond/hole-02-aerial-bluewater.png --style-ref refs/hole-07-original.png --ip-mode style --ip-scale 1.0 --strength 0.95 --controlnet-scale 0.8 --prompt painted --measure --out out/hole2
echo "[$(date '+%H:%M:%S')] SWEEP DONE"
