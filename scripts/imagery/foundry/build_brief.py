"""Build the one-page brief (Artifact HTML + vault Markdown) from final/hole-NN.json results.

Usage: .venv/bin/python build_brief.py [--out brief] [--vault]
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
TOL = 5.0


def b64jpg(im: Image.Image, q: int = 82, maxw: int = 1400) -> str:
    if im.width > maxw:
        im = im.resize((maxw, int(im.height * maxw / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def load_results() -> list[dict]:
    rows = []
    for h in range(1, 19):
        p = HERE / "final" / f"hole-{h:02d}.json"
        if not p.exists():
            rows.append({"hole": h, "missing": True})
            continue
        m = json.loads(p.read_text())
        b = m["best"]
        rows.append({
            "hole": h, "missing": False,
            "skelAerMax": m["skeletonVsAerial"]["maxYards"], "skelAerMed": m["skeletonVsAerial"]["medianYards"],
            "cardSkelMax": b["vsSkeleton150"]["landMaxYards"], "cardSkelMed": b["vsSkeleton150"]["landMedianYards"],
            "cardAerMax": b["vsAerial150"]["landMaxYards"], "cardAerMed": b["vsAerial150"]["landMedianYards"],
            "waterTiles": b["vsAerial150"]["tilesWater"], "waterMax": b["vsAerial150"]["waterMaxYards"],
            "attempt": b["attempt"], "frame": b["frameFound"], "snapMed": b["snapMedianPx"],
            "pass": bool(m["pass"]), "seconds": m.get("secondsTotal", 0),
        })
    return rows


def card_strip(holes: list[int]) -> Image.Image:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    W, H, pad = 260, 347, 8
    strip = Image.new("RGB", (pad + len(holes) * (W + pad), H + 34 + pad), "#14261c")
    d = ImageDraw.Draw(strip)
    for i, h in enumerate(holes):
        p = HERE / "final" / f"hole-{h:02d}.png"
        x = pad + i * (W + pad)
        if p.exists():
            strip.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (x, 30))
        d.text((x + 2, 4), f"Hole {h}", fill="#efe7d2", font=f)
    return strip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "brief")
    ap.add_argument("--vault", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)
    rows = load_results()
    done = [r for r in rows if not r["missing"]]
    passed = [r for r in done if r["pass"]]
    worst = max((r["cardSkelMax"] for r in done), default=0)
    med_all = sorted(r["cardSkelMed"] for r in done)
    med_mid = med_all[len(med_all) // 2] if med_all else 0
    today = date.today().isoformat()

    # images
    finals_sheet = HERE / "sheets" / "gptimage2-finals.jpg"
    img_finals = b64jpg(Image.open(finals_sheet)) if finals_sheet.exists() else ""
    strip_holes = [h for h in (1, 4, 7, 10, 14, 18) if (HERE / "final" / f"hole-{h:02d}.png").exists()]
    img_strip = b64jpg(card_strip(strip_holes), maxw=1560) if strip_holes else ""
    sk7 = HERE / "cond" / "hole-07-base-v6.png"
    or7 = HERE / "refs" / "hole-07-original.png"
    fi7 = HERE / "final" / "hole-07.png"
    trio = ""
    if sk7.exists() and or7.exists() and fi7.exists():
        ims = [Image.open(or7).convert("RGB").resize((300, 400)), Image.open(sk7).convert("RGB").resize((300, 400)), Image.open(fi7).convert("RGB").resize((300, 400))]
        t = Image.new("RGB", (3 * 310 + 10, 400 + 20), "#14261c")
        for i, im in enumerate(ims):
            t.paste(im, (10 + i * 310, 10))
        trio = b64jpg(t, q=86, maxw=940)

    # scorecard strip + table
    cells = []
    for r in rows:
        if r["missing"]:
            cells.append(f'<div class="cell pending"><span class="n">{r["hole"]}</span><span class="v">—</span></div>')
        else:
            cls = "ok" if r["pass"] else "bad"
            cells.append(f'<div class="cell {cls}"><span class="n">{r["hole"]}</span><span class="v">{r["cardSkelMax"]:.1f}</span></div>')
    trs = []
    for r in rows:
        if r["missing"]:
            trs.append(f'<tr><td>{r["hole"]}</td><td colspan="6" class="muted">not rendered</td></tr>')
            continue
        water = f'{r["waterTiles"]} · ≤{r["waterMax"]:.1f}' if r["waterTiles"] else "—"
        verdict = '<span class="pill ok">pass</span>' if r["pass"] else '<span class="pill bad">fail</span>'
        trs.append(f'<tr><td>{r["hole"]}</td><td>{r["skelAerMax"]:.2f}</td><td><b>{r["cardSkelMax"]:.2f}</b> · {r["cardSkelMed"]:.2f}</td>'
                   f'<td>{r["cardAerMax"]:.1f} · {r["cardAerMed"]:.2f}</td><td>{water}</td><td>{r["attempt"]}</td><td>{verdict}</td></tr>')

    html_doc = TEMPLATE.format(
        title="Peach Tree Hole Cards", today=today, n_done=len(done), n_pass=len(passed), worst=worst, med_mid=med_mid,
        cells="".join(cells), rows="".join(trs), img_finals=img_finals, img_strip=img_strip, trio=trio,
    )
    # encoding-proof: entities instead of raw typographic characters (local previews may lack a charset header)
    for a, b in (("—", "&mdash;"), ("·", "&middot;"), ("≤", "&le;"), ("→", "&rarr;"), ("×", "&times;"), ("’", "&rsquo;"), ("“", "&ldquo;"), ("”", "&rdquo;"), ("–", "&ndash;")):
        html_doc = html_doc.replace(a, b)
    out_html = args.out / "peach-tree-hole-cards.html"
    out_html.write_text(html_doc, encoding="utf-8")
    print("wrote", out_html, f"{out_html.stat().st_size/1e6:.1f} MB")

    if args.vault:
        md = MD_TEMPLATE.format(
            today=today, n_done=len(done), n_pass=len(passed), worst=worst, med_mid=med_mid,
            table="\n".join(
                f"| {r['hole']} | {'—' if r['missing'] else f'{r['skelAerMax']:.2f}'} | "
                f"{'—' if r['missing'] else f'{r['cardSkelMax']:.2f} / {r['cardSkelMed']:.2f}'} | "
                f"{'—' if r['missing'] else f'{r['cardAerMax']:.1f} / {r['cardAerMed']:.2f}'} | "
                f"{'—' if r['missing'] else (f'{r['waterTiles']} · ≤{r['waterMax']:.1f}' if r['waterTiles'] else '—')} | "
                f"{'—' if r['missing'] else ('PASS' if r['pass'] else 'FAIL')} |"
                for r in rows),
        )
        vault = Path.home() / "AriesHQ/Projects/Golf" / f"Peach Tree Hole Cards - Accurate and Beautiful Process {today}.md"
        vault.write_text(md)
        print("wrote", vault)


TEMPLATE = """<title>{title}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Literata:opsz,wght@7..72,400;7..72,500;7..72,600&display=swap">
<style>
:root {{
  --paper:#f3eedf; --ink:#1b2a1f; --ink-2:#4a5a4c; --rule:#d9cfb4; --fairway:#2e6b3a; --gold:#c99f3f; --water:#2c6f9c; --sand:#e6d6ae;
  --ok:#2e6b3a; --bad:#a33a2a; --pend:#8e927f; --surface:#ebe4d0; --surface-2:#e2dac3;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#14261c; --ink:#efe7d2; --ink-2:#b9c2ad; --rule:#2b4a36; --fairway:#7cc56f; --gold:#d8b257; --water:#6fb0dd; --sand:#d9c79b;
    --ok:#7cc56f; --bad:#ff9d8c; --pend:#8a9a8b; --surface:#1b3325; --surface-2:#223f2e;
  }}
}}
:root[data-theme="dark"] {{
  --paper:#14261c; --ink:#efe7d2; --ink-2:#b9c2ad; --rule:#2b4a36; --fairway:#7cc56f; --gold:#d8b257; --water:#6fb0dd; --sand:#d9c79b;
  --ok:#7cc56f; --bad:#ff9d8c; --pend:#8a9a8b; --surface:#1b3325; --surface-2:#223f2e;
}}
body {{ background:var(--paper); color:var(--ink); font-family:Literata, Georgia, "Times New Roman", serif; font-size:17px; line-height:1.55; margin:0; }}
main {{ max-width:780px; margin:0 auto; padding:40px 22px 72px; }}
h1,h2,h3,.disp {{ font-family:"Barlow Condensed","Arial Narrow","Helvetica Neue",Arial,sans-serif; letter-spacing:.01em; text-wrap:balance; }}
h1 {{ font-size:52px; line-height:1; font-weight:700; margin:0 0 6px; }}
h2 {{ font-size:26px; font-weight:600; margin:44px 0 10px; padding-top:18px; border-top:2px solid var(--gold); }}
h3 {{ font-size:19px; font-weight:600; margin:18px 0 4px; }}
p {{ margin:0 0 12px; max-width:68ch; }}
.kicker {{ font-family:"Barlow Condensed",sans-serif; text-transform:uppercase; letter-spacing:.12em; font-size:13px; color:var(--ink-2); }}
.lede {{ font-size:19px; color:var(--ink); max-width:62ch; }}
.muted {{ color:var(--ink-2); }}
.score {{ display:grid; grid-template-columns:repeat(18,1fr); gap:4px; margin:22px 0 6px; }}
.cell {{ background:var(--surface); border-bottom:4px solid var(--pend); padding:6px 2px 4px; text-align:center; font-family:"Barlow Condensed",sans-serif; font-variant-numeric:tabular-nums; }}
.cell .n {{ display:block; font-size:12px; color:var(--ink-2); letter-spacing:.06em; }}
.cell .v {{ display:block; font-size:19px; font-weight:600; line-height:1.1; }}
.cell.ok {{ border-bottom-color:var(--ok); }} .cell.bad {{ border-bottom-color:var(--bad); }} .cell.pending {{ opacity:.6; }}
.caption {{ font-size:14px; color:var(--ink-2); margin:6px 0 0; }}
.steps {{ counter-reset:s; display:grid; gap:12px; margin:14px 0 0; padding:0; list-style:none; }}
.steps li {{ display:grid; grid-template-columns:44px 1fr; gap:12px; align-items:start; }}
.steps li::before {{ counter-increment:s; content:counter(s); font-family:"Barlow Condensed",sans-serif; font-size:30px; font-weight:700; line-height:1; color:var(--gold); }}
.steps li > div > b {{ font-family:"Barlow Condensed",sans-serif; font-size:19px; font-weight:600; display:block; }}
.steps p {{ margin:2px 0 0; font-size:16px; }}
figure {{ margin:16px 0 0; }}
figure img {{ width:100%; height:auto; display:block; border:1px solid var(--rule); }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-family:"Barlow Condensed",sans-serif; font-size:16px; font-variant-numeric:tabular-nums; }}
th {{ text-align:left; font-weight:600; color:var(--ink-2); text-transform:uppercase; letter-spacing:.06em; font-size:12px; padding:8px 8px 6px; border-bottom:1px solid var(--rule); }}
td {{ padding:6px 8px; border-bottom:1px solid var(--rule); white-space:nowrap; }}
.pill {{ display:inline-block; padding:1px 8px; border-radius:3px; font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--paper); }}
.pill.ok {{ background:var(--ok); }} .pill.bad {{ background:var(--bad); }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px 28px; }}
@media (max-width:640px) {{ .grid2 {{ grid-template-columns:1fr; }} h1 {{ font-size:40px; }} .score {{ grid-template-columns:repeat(9,1fr); }} }}
.rule {{ height:2px; background:var(--gold); width:64px; margin:10px 0 22px; }}
.dec {{ background:var(--surface); padding:14px 16px; border-left:4px solid var(--gold); }}
.dec p {{ margin:0 0 6px; font-size:16px; }}
</style>
<main>
  <div class="kicker">Peach Tree Golf &amp; Country Club · Marysville · {today}</div>
  <h1>Peach Tree Hole Cards</h1>
  <div class="rule"></div>
  <p class="lede">The hole art you like, with yardages you can trust. One process, six steps, measured on every hole. This page is the whole thing — what it is, how it works, how it did on all 18, and the two calls only you can make.</p>

  <div class="score">{cells}</div>
  <p class="caption">All 18 holes. The number is the worst tile drift on that hole's finished card, in yards, against its exact skeleton. Green = under 5 yd. {n_pass} of {n_done} rendered holes pass; worst card {worst:.1f} yd, typical {med_mid:.2f} yd.</p>

  <h2>The idea in one line</h2>
  <p>Don't ask the AI to repaint the photo and hope it stays put. Draw the hole first from real shapes, let the AI paint <em>over the drawing</em>, snap the painting back onto the drawing, and measure the difference before a single yardage is drawn on it.</p>

  <figure><img src="{trio}" alt="Hole 7: the original art, the skeleton, and the finished card"><figcaption class="caption">Hole 7, left to right: your original illustration (the look we're matching), the skeleton (exact geometry), the finished card.</figcaption></figure>

  <h2>The process</h2>
  <ol class="steps">
    <li><div><b>Skeleton</b><p>Every fairway, green, tee, bunker, pond, cart path and hole line comes from OpenStreetMap's survey of Peach Tree, projected through the app's own card math. Trees and dry ground are read off the 2022 aerial. Drawn like a yardage book: mow stripes, modeled crowns, long shadows. It sits <strong>0.01 yd</strong> from the aerial.</p></div></li>
    <li><div><b>Frame</b><p>The skeleton is padded to the painter's aspect ratio with a thin white border. The border is a fiducial — without it the painter quietly re-crops by a few percent (4 yd of error); with it, framing holds.</p></div></li>
    <li><div><b>Paint</b><p>gpt-image-2 — the same family that made your originals — repaints the skeleton in the style of your hole-by-hole art with one instruction: geometry is sacred. Runs through the Codex sign-in already on the Mac Studio; about a minute a hole, no API key.</p></div></li>
    <li><div><b>Snap</b><p>The painting is cropped to its frame and re-aligned to the skeleton: a global fit, then a gentle local snap of one or two pixels. It moves paint by less than a yard; it never moves the map.</p></div></li>
    <li><div><b>Gate</b><p>Drift is measured in yards on a grid of tiles, two ways: finished card against the skeleton (did the painter move anything?) and skeleton against the aerial (is the map right?). Water is scored separately, because OpenStreetMap's shoreline and the 2022 drought photo disagree — that's a question for you, not an error. Over 5 yd on any land tile = the card does not ship with numbers on it.</p></div></li>
    <li><div><b>Ship</b><p>Passing cards replace the illustrated set; the yardage band, pin and GPS dot already read from the same geometry, so nothing else in the app changes.</p></div></li>
  </ol>

  <h2>Proof</h2>
  <figure><img src="{img_finals}" alt="Holes 7 and 2: original, skeleton, finished card, close-ups"><figcaption class="caption">Holes 7 and 2 — original, skeleton, finished card and close-ups. Hole 7: 0.41 yd max / 0.06 median vs skeleton. Hole 2: 0.53 / 0.10 (and 0.55 vs the real aerial).</figcaption></figure>
  <figure><img src="{img_strip}" alt="A strip of finished cards across the course"><figcaption class="caption">Finished cards across the course.</figcaption></figure>

  <h2>The numbers, all 18</h2>
  <div class="wrap"><table>
    <thead><tr><th>Hole</th><th>Skeleton vs aerial (yd)</th><th>Card vs skeleton · max · median</th><th>Card vs aerial</th><th>Water tiles · offset</th><th>Paint tries</th><th>Verdict</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="caption">"Card vs aerial" is the harshest comparison: where paint replaced photo texture the measuring tool sometimes loses grip, which is why the card-vs-skeleton number is the gate and this one is context.</p>

  <h2>What was ruled out (measured, not guessed)</h2>
  <div class="grid2">
    <div><h3>Rescuing the original 18</h3><p class="muted">They are reimaginings — hole 7's pond, green and cart path sit elsewhere. No warp gets them under 5 yd (best: 11 yd).</p></div>
    <div><h3>Repainting the photo</h3><p class="muted">Holds geometry, never looks like anything but an aerial.</p></div>
    <div><h3>Edge-only control</h3><p class="muted">Gets the look, invents lakes and bunkers (9–15 yd).</p></div>
    <div><h3>Open SDXL painters over the skeleton</h3><p class="muted">Accurate (0.1–0.6 yd) but flat and muted — "not at the acceptable level." Kept as a free fallback.</p></div>
  </div>

  <h2>Your two calls</h2>
  <div class="dec">
    <p><b>1. Hole 7's pond.</b> OpenStreetMap draws it much larger than the 2022 drought aerial shows. Which shoreline is true today decides how that card is drawn.</p>
    <p><b>2. Ship this look.</b> If the finished cards above meet your bar, the next steps are mechanical: WebP/AVIF derivatives, a PR, and the hole-6 / hole-8 tree checks against your own eyes.</p>
  </div>

  <h2>Where it lives</h2>
  <p class="muted">Mac Studio: <code>~/rex/peach-tree-imagery/</code> (scripts, skeletons, finals, logs). Repo branch <code>foundry-skeleton-imagery</code> → <code>scripts/imagery/foundry/</code> with the README. Vault: the Peach Tree prototype note and this brief. Linear: MAR-39.</p>
</main>
"""

MD_TEMPLATE = """# Peach Tree Hole Cards — the accurate-and-beautiful process ({today})

**One line:** draw each hole from real shapes, let gpt-image-2 paint over the drawing in the style of
Mario's original art, snap the painting back onto the drawing, measure drift in yards, ship only
what passes. {n_pass} of {n_done} rendered holes pass the 5-yd gate; worst card {worst:.1f} yd, typical {med_mid:.2f} yd.

## Steps
1. **Skeleton** — OSM fairways/greens/tees/bunkers/water/cart paths/hole line through the app's card
   transform + trees/dry ground from the 2022 aerial, drawn yardage-book style (`make_base_map.py
   --procedural --dry-sigma 4 --detail 1.0`). 0.01 yd from the aerial.
2. **Frame** — pad to 2:3 with a thin white border (fiducial; without it gpt-image-2 re-crops ~4 yd).
3. **Paint** — gpt-image-2 via Hermes `image_gen/openai-codex` (Codex OAuth, ~1 min/hole), style ref =
   the hole's original illustration, prompt "geometry is sacred" (`gpt_image_render.py`).
4. **Snap** — crop to frame, ECC global affine + gentle dense snap (~1.5 px) onto the skeleton.
5. **Gate** — `measure_drift_classed.py`: card-vs-skeleton (the gate, land tiles, ≤5 yd), skeleton-vs-
   aerial, card-vs-aerial (context), water tiles separate (OSM vs 2022 shoreline = Mario's call).
6. **Ship** — passing cards replace the illustrated set; band/pin/GPS already read the same geometry.

Orchestration: `pipeline_hole.py --hole N` (all of the above, 2 paint attempts) and `run_all.sh`.

## Results
| Hole | Skeleton vs aerial | Card vs skeleton max / median | Card vs aerial max / median | Water tiles · offset | Verdict |
|---|---|---|---|---|---|
{table}

## Ruled out (measured)
Rescuing the original 18 by warping (reimaginings, best 11 yd); repainting the photo (accurate, still an
aerial); edge-only control (pretty, invents 9–15 yd); open SDXL painters over the skeleton (0.1–0.6 yd
but flat — Mario: not acceptable; kept as the free fallback).

## Mario's calls
1. Hole 7 pond — OSM shoreline vs 2022 drought aerial. 2. Ship this look → WebP/AVIF, PR, hole 6/8 tree checks.

Rig: `~/rex/peach-tree-imagery/`; repo branch `foundry-skeleton-imagery` (`scripts/imagery/foundry/`); Linear MAR-39.
"""

if __name__ == "__main__":
    main()
