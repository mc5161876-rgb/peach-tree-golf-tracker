# Foundry imagery rig — paint over a skeleton, not over the photo (2026-08-22)

Runs on the Mac Studio (Apple Silicon, MPS; 35–43 s per 1× card, ~80 s at 2×). Working
copy lives in `~/rex/peach-tree-imagery/` with its own uv venv and ~30 GB of models under
`hf-cache/` (SDXL base, Juggernaut XL v9, DreamShaper XL, xinsir tile/canny/depth
ControlNets, IP-Adapter ViT-H, fp16-fix VAE). `setup-foundry.sh` rebuilds it.

## The method

1. `make_base_map.py --hole N --detail 1.0 --procedural --dry-sigma 4` renders a **skeleton**
   card from real geometry: OSM fairways/greens/tees/bunkers/water/hole line projected through
   the app's own card transform (`sources.json` cardGeometry), trees and dry ground classified
   off the NAIP aerial, a high-pass of the aerial blended in, then mow stripes, modeled tree
   crowns with late-afternoon shadows, grain, water gradient. Skeleton vs aerial: 0.00–0.02 yd.
2. `generate_styled_card.py --aerial <skeleton> --base juggernaut --control tile
   --controlnet-scale 0.8 --ip-mode style --ip-scale 0.8 --strength 0.6 --prompt cinematic
   --work-scale 2 --style-ref <one of the original illustrations>` paints realism over it.
   2× is tightest and sharpest (hole 7: 0.94 yd, hole 2: 0.36 yd vs the aerial).
3. `grade_card.py` colour-grades toward the original art (Reinhard Lab transfer; pixels do
   not move). The graded skeleton alone, with no AI paint, is also a valid look.
4. Gate: `measure_drift_classed.py` — report skeleton-vs-aerial AND painted-vs-skeleton,
   land tiles only; water tiles separately (OSM shoreline vs 2022 drought aerial is a
   ground-truth question, not drift). `reclass.py` annotates sidecars; `make_style_sheet.py`
   builds contact sheets.

## Dead ends, measured (do not repeat)

- Warping the original free-form illustrations onto the geometry (`register_art.py`,
  self-tested): impossible — they are reimaginings (hole 7 14→11.5 yd, hole 2 32→34 yd).
- Tile ControlNet over the aerial + style ref: accurate, still looks like an aerial.
- Canny / depth / tile+canny control, tile grip < 0.8, IP "full" mode: pretty, invents
  (9–15 yd).

`sweeps/` are the exact command records; `evidence/` the sheets shown to Mario.
Nothing here is authoritative course data.
