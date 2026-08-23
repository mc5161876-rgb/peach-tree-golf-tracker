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

## Update, same night — the look is solved with gpt-image-2 over the skeleton

`gpt_image_render.py` (run with the Hermes venv; uses Hermes' `image_gen/openai-codex`
plugin = gpt-image-2 via Codex OAuth, ~55 s/image at `high`): feed the **framed** 2:3 padded
skeleton plus the original illustration as style reference, prompt "geometry is sacred".
Then crop to the frame, ECC global affine + gentle dense snap (`register_art.register_dense`,
coarse tiles, ~1.5 px median) onto the skeleton, then gate. Hole 7: 0.41 yd max / 0.06
median vs skeleton; hole 2: 0.53 / 0.10 (and 0.55 vs the real aerial). Evidence:
`evidence/gptimage2-finals.jpg`. The white frame matters: unframed, the model re-crops by a
few percent (4 yd median raw).

## 18-hole run, 2026-08-22 21:03 — 18/18 pass

`pipeline_hole.py --hole N` runs the whole chain (skeleton → frame → gpt-image-2 → crop → ECC +
snap → gate → final/hole-NN.png + .json + sheet); `run_all.sh` loops the course. Results in
`results-2026-08-22/` (sidecars) and `evidence/all-18-finals.jpg`. Worst card 4.52 yd (hole 7,
second paint attempt), median of medians 0.08 yd, two holes needed a second paint (7, 11),
21 minutes end to end. Finished cards themselves are in the vault: `Projects/Golf/Hole Cards
2026-08-22/cards/` (not committed here — 27 MB; they enter the repo via the shipping PR once
Mario approves the look). `build_brief.py` renders the one-page brief (Artifact + vault note).
