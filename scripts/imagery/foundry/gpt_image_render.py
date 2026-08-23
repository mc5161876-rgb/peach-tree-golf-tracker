"""Render a skeleton card with gpt-image-2 (via Hermes' Codex OAuth plugin) in the style of an
original illustration, asking it to keep every shape exactly. Output is cropped back to the
900x1200 card frame. Drift is measured afterwards with the imagery venv (reclass.py).

Run with the Hermes venv:  ~/.hermes/hermes-agent/venv/bin/python gpt_image_render.py --hole 7 ...
"""
from __future__ import annotations
import argparse, importlib.util, json, os, shutil, sys, time
from pathlib import Path
from PIL import Image

HERMES = Path.home() / ".hermes/hermes-agent"
sys.path.insert(0, str(HERMES))
os.environ.setdefault("OPENAI_IMAGE_MODEL", "gpt-image-2-high")
spec = importlib.util.spec_from_file_location("codex_imggen", HERMES / "plugins/image_gen/openai-codex/__init__.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

PROMPT = (
    "Repaint the FIRST image (a top-down golf hole map) as a premium, photorealistic cinematic 2.5D "
    "yardage-book illustration in exactly the visual style of the SECOND image: lush manicured grass with "
    "visible mow stripes, individually modeled tree canopies with long warm late-afternoon shadows, clean "
    "sculpted sand bunkers, clear deep blue water, dry golden rough, rich saturated colour, crisp detail. "
    "CRITICAL: this is a map, so geometry is sacred. Keep every shape, outline, position and size EXACTLY as "
    "in the first image: fairways, greens, tees, bunkers, water, tree clusters, cart paths, the gold hole "
    "line and its two markers, and the framing/crop. Do not add, remove, move, resize or reshape any feature. "
    "Do not add text, labels, people, carts, buildings, roads or new water. Same straight-down orthographic view."
)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--skeleton", type=Path, required=True, help="2:3 padded skeleton (900x1350)")
    ap.add_argument("--style-ref", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--prompt", default=PROMPT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    prov = mod.OpenAICodexImageGenProvider()
    print("provider available:", prov.is_available(), "| model:", mod._resolve_model()[0], flush=True)
    t0 = time.time()
    res = prov.generate(args.prompt, aspect_ratio="portrait", image_url=str(args.skeleton), reference_image_urls=[str(args.style_ref)])
    secs = round(time.time() - t0, 1)
    if not res.get("success"):
        print("FAILED:", json.dumps(res, indent=1, default=str)[:1500]); sys.exit(1)
    src = Path(res["image"]); raw = Image.open(src).convert("RGB")
    print(f"got {raw.size} in {secs}s from {src.name} (source={res.get('image_source')})", flush=True)
    stem = f"hole-{args.hole:02d}-gptimage2{args.tag}"
    shutil.copy(src, args.out / f"{stem}-raw.png")
    # back to card space: 1024x1536 -> 900x1350 -> centre crop 900x1200
    im = raw.resize((900, 1350), Image.LANCZOS).crop((0, 75, 900, 1275))
    im.save(args.out / f"{stem}.png")
    json.dump({"hole": args.hole, "skeleton": str(args.skeleton), "styleRef": str(args.style_ref), "model": res.get("model"),
               "size": res.get("size"), "quality": res.get("quality"), "prompt": args.prompt, "secondsTaken": secs,
               "raw": str(args.out / f"{stem}-raw.png")}, open(args.out / f"{stem}.json", "w"), indent=2)
    print("saved", args.out / f"{stem}.png")

if __name__ == "__main__":
    main()
