# Geometry-locked hole imagery — what the measurements say

Answers MAR-28: can a hole card be both better-looking than the raw aerial and
accurate enough to read a yardage off? Measured on holes 7 and 2, 2026-07-26.

**Short answer: accurate, yes, comfortably. Better-looking in the way the
current illustrated art is — no, not while geometry holds.**

## How far the current art drifts

The baseline this had to beat. Existing illustrated cards, measured against
their own aerials:

| Hole | Max drift | Median | At 5 yd |
| --- | --- | --- | --- |
| 7 | 16.81 yd | 4.69 yd | FAIL |
| 2 | 38.66 yd | 16.85 yd | FAIL |

Hole 2 is off by more than a full club almost everywhere. Hole 7 is the more
instructive failure: its median is 4.69 yards, inside the bar, while its worst
region is 16.81. Most of that card is fine and one part is badly wrong, which
is precisely the shape that produces a single confidently wrong number.

This is not an argument about how those cards were made. It is a measurement of
what they are.

## Denoise strength is not the dial

The first sweep moved denoise strength from 0.25 to 0.75 — three times the
departure from the source — while the ControlNet conditioning scale sat at 0.9.

| Strength | Hole 7 max | Hole 2 max |
| --- | --- | --- |
| 0.25 | 0.36 yd | 0.76 yd |
| 0.35 | 0.51 yd | 0.82 yd |
| 0.45 | 0.47 yd | 7.07 yd |
| 0.60 | 0.74 yd | not run |
| 0.75 | 0.43 yd | not run |

Drift stayed flat and so did the look. At a conditioning scale of 0.9 the
control signal dominates and strength barely matters. Anyone reading a
strength-only sweep as "the trade-off curve" is reading the wrong axis.

Hole 2 at 0.45 is the exception worth noting: median 0.40 yd, max 7.07. A
single region invented something. Nothing about the setting predicts which.

## The conditioning scale is the dial, and it falls off a cliff

Strength held at 0.60, conditioning scale swept:

| Conditioning | Max drift | Median | At 5 yd |
| --- | --- | --- | --- |
| 0.90 | 0.74 yd | 0.20 yd | PASS |
| 0.70 | 7.26 yd | 0.25 yd | FAIL |
| 0.50 | 9.96 yd | 0.41 yd | FAIL |
| 0.30 | 11.19 yd | 1.12 yd | FAIL |

There is no sweet spot to hunt for. One step below 0.9 and the bar is already
broken by 45%. And again the medians stay low while the maxima blow out — the
model keeps most of the card and reinvents patches of it. At 0.30 there are
bunkers on the right of hole 7 that do not exist on the ground.

## What the passing setting actually looks like

A cleaner aerial. Better colour, crisper tree canopies, less of the mush that
makes NAIP look like a screenshot. It is a real improvement on the source and
it is not artwork.

The cinematic quality of the current illustrated set — modelled light, depth,
painted canopies — never appears at any passing setting. It cannot, because
that look *is* the model reinterpreting the hole, and reinterpreting the hole
is the same operation as moving it.

## Recommendation

**Use strength 0.35, conditioning scale 0.90.** It sits at 0.51 yd on hole 7
and 0.82 on hole 2, roughly a tenth of the tolerance, with margin for holes not
yet tested. Higher strengths measured no worse but buy nothing visible, and
lower conditioning is off the cliff.

**The 5-yard bar is reachable, with room to spare — but only for a sharpened
aerial.** If the painterly look is required, it has to be decorative and carry
no yardages.

**Do not generate the remaining 16 holes yet.** Every card measured here is
framed at 1.78x the hole's own length (MAR-31), so detail is spread thin across
neighbouring holes. At 1.25x framing the repaint gets far more pixels on the
hole itself and may look materially better for the same drift. Re-take the
judgement on tight cards before committing to a set of 18.

## Reproducing this

Venv, outside the repo, Python 3.12:
`C:\Users\mc516\Documents\Aries Radar\peach-tree-imagery\.venv`

Models cached at `peach-tree-imagery\hf-cache` (9 GB), also outside the repo.
SDXL base 1.0 plus `xinsir/controlnet-tile-sdxl-1.0`, both ungated — no
HuggingFace token needed. torch 2.6.0+cu124 on an RTX 4070 Ti.

```
python scripts/imagery/generate_locked_card.py --hole 7 \
    --out <outside-repo> --strength 0.35 --controlnet-scale 0.90

python scripts/imagery/measure_drift.py --hole 7 \
    --reference public/course/peach-tree/hole-07.webp \
    --candidate <generated.png> --json drift.json

python scripts/imagery/make_comparison.py --hole 7 \
    --aerial ... --illustrated ... --generated ... --drift drift.json --out sheet.png
```

Work happens at 960x1280 — the card's exact 3:4 ratio on a 64-pixel grid — then
resizes to 900x1200. The card size itself is unusable directly: 900 is not a
multiple of 8, and any working size with a different aspect would stretch one
axis and register as drift the model never caused.

Every image is written with a JSON sidecar recording seed, strength,
conditioning scale, steps, guidance, both prompts, and the torch version. A
result whose settings are unknown is not evidence.

Reproducibility was checked rather than assumed: hole 7 regenerated at strength
0.35, conditioning 0.90, seed 20260726 came back **byte-identical** to the
original run (md5 `e7d8906288bd82ae6ae637769c0dbefd`). Every number above can
be reproduced on this machine, not merely approximated.
