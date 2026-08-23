#!/bin/zsh
# All 18 holes through pipeline_hole.py, sequentially (gpt-image-2 calls are the bottleneck, ~1 min each).
cd ~/rex/peach-tree-imagery
export HF_HOME=~/rex/peach-tree-imagery/hf-cache
for H in 7 2 1 3 4 5 6 8 9 10 11 12 13 14 15 16 17 18; do
  echo "[$(date '+%H:%M:%S')] === hole $H ==="
  .venv/bin/python pipeline_hole.py --hole $H --attempts 2 2>&1 | grep -v "^\s*$" | grep -v "Warning\|warn" 
done
echo "[$(date '+%H:%M:%S')] ALL DONE"
