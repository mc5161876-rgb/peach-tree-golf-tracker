"""Repaint a hole card in the look of a reference illustration without moving anything on it.

Sibling of the repo's scripts/imagery/generate_locked_card.py (MAR-28), with three changes:

1. Runs on Apple Silicon (MPS) as well as CUDA. Foundry has 96 GB of unified memory, so
   nothing needs offloading.
2. Adds an IP-Adapter *style* reference. The aerial still goes in as the img2img start image
   and as ControlNet conditioning — that is what holds the geometry — but the look (light,
   palette, how trees and grass are rendered) is taken from a reference image, e.g. one of
   the original free-form illustrations Mario likes. With InstantStyle block targeting the
   adapter feeds only the style-carrying attention blocks, so the reference's *layout* is
   not copied in — which matters, because those originals are reimaginings of the hole and
   copying their layout is exactly the drift being avoided.
3. Lets the ControlNet be chosen: `tile` (pins pixels — faithful but suppresses style),
   `canny` / `depth` (pin edges or relief, leave colour and texture free), or `tile+canny`
   (MultiControlNet, tile at low weight for placement, canny for crisp shapes).

As before: nothing here is authoritative course data, and measure_drift.py decides whether a
card earned the right to carry a number. Every output gets a JSON sidecar with its settings
and, with --measure, its drift.

Typical:
  python generate_styled_card.py --hole 7 --style-ref refs/hole-07-original.png \
      --control canny --strength 0.95 --controlnet-scale 0.7 --ip-scale 1.0 --ip-mode style \
      --prompt painted --out out/hole7 --measure
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from diffusers import AutoencoderKL, ControlNetModel, StableDiffusionXLControlNetImg2ImgPipeline
from PIL import Image

WORK_SIZE = (960, 1280)  # SDXL needs a 64-px grid; 960x1280 keeps the card's exact 3:4 ratio
CARD_SIZE = (900, 1200)

BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
BASES = {
    "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
    "juggernaut": "RunDiffusion/Juggernaut-XL-v9",
    "dreamshaper": "Lykon/dreamshaper-xl-1-0",
}
VAE_FIX = "madebyollin/sdxl-vae-fp16-fix"  # SDXL's own VAE produces NaNs in fp16
CONTROLNETS = {
    "tile": "xinsir/controlnet-tile-sdxl-1.0",
    "canny": "xinsir/controlnet-canny-sdxl-1.0",
    "depth": "xinsir/controlnet-depth-sdxl-1.0",
}
CONTROL_COMBOS = {
    "tile": ["tile"],
    "canny": ["canny"],
    "depth": ["depth"],
    "tile+canny": ["tile", "canny"],
    "canny+depth": ["canny", "depth"],
}
IP_ADAPTER_REPO = "h94/IP-Adapter"
IP_ADAPTERS = {
    "vit-h": ("sdxl_models", "ip-adapter_sdxl_vit-h.safetensors"),
    "plus-vit-h": ("sdxl_models", "ip-adapter-plus_sdxl_vit-h.safetensors"),
}
IP_IMAGE_ENCODER = "models/image_encoder"  # ViT-H, shared by both adapters above

# Prompt families copied from the repo's generate_locked_card.py (branch option2-painterly-style)
# so results stay comparable with the MAR-28/MAR-39 sweeps. Keep every prompt under CLIP's
# 77-token limit — diffusers only warns, and the tail silently vanishes.
PROMPTS = {
    "photo": (
        "aerial photograph of a golf hole at a private country club, "
        "manicured fairway and rough, mown grass banding, bunkers with clean sand, "
        "mature valley oak canopies casting soft shadows, "
        "pond with clear deep blue water and crisp banks, "
        "distinct individual trees at the water's edge, golden hour light, "
        "rich natural colour, crisp detail, photographic, top-down",
        "illustration, cartoon, painting, cgi render, map, diagram, text, labels, "
        "watermark, buildings added, roads added, distorted, warped, blurry, "
        "algae, pond scum, murky green water, muddy water",
    ),
    "painted": (
        "premium hand-painted yardage book illustration of a golf hole, aerial "
        "view, stylized manicured fairway and green with elegant mow lines, "
        "painterly valley oak canopies, clean sculpted sand bunkers, pond with "
        "clear deep blue water, crisp trees at the pond edge, warm golden light, "
        "rich saturated colour, top-down",
        "photograph, satellite image, map, diagram, text, labels, watermark, "
        "buildings added, roads added, distorted, warped, blurry, "
        "algae, pond scum, murky green water, muddy water",
    ),
    # Lets the style reference do the talking: content words only, no look words.
    "neutral": (
        "aerial view of a golf hole, fairway, green, sand bunkers, trees, pond with clear blue water, top-down",
        "text, labels, watermark, buildings added, roads added, distorted, warped, blurry, "
        "algae, murky green water",
    ),
    # The look of the originals, in words: cinematic 2.5D yardage-book render.
    "cinematic": (
        "cinematic 2.5D aerial render of a golf hole, premium yardage book art, lush vivid fairway "
        "and green, modeled tree canopies with long warm shadows, sculpted bunkers, clear deep "
        "blue pond, dry golden rough, late afternoon sun, rich saturated colour, top-down",
        "photograph, satellite image, flat, washed out, map, diagram, text, labels, watermark, "
        "buildings added, roads added, distorted, warped, blurry, algae, murky green water",
    ),
}

# InstantStyle block targeting (diffusers set_ip_adapter_scale dict form).
IP_MODES = {
    "full": None,  # scalar scale everywhere: transfers style AND tends to copy layout
    "style": {"up": {"block_0": [0.0, 1.0, 0.0]}},
    "style-layout": {"down": {"block_2": [0.0, 1.0]}, "up": {"block_0": [0.0, 1.0, 0.0]}},
}


def pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_pipeline(device: str, cache_dir: Path, adapter: str, dtype: torch.dtype, control: str, base: str = BASE_MODEL):
    names = CONTROL_COMBOS[control]
    nets = [ControlNetModel.from_pretrained(CONTROLNETS[n], torch_dtype=dtype, cache_dir=cache_dir) for n in names]
    controlnet = nets[0] if len(nets) == 1 else nets
    vae = AutoencoderKL.from_pretrained(VAE_FIX, torch_dtype=dtype, cache_dir=cache_dir)
    pipeline = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
        base,
        controlnet=controlnet,
        vae=vae,
        torch_dtype=dtype,
        variant="fp16",
        use_safetensors=True,
        cache_dir=cache_dir,
    )
    subfolder, weight = IP_ADAPTERS[adapter]
    pipeline.load_ip_adapter(
        IP_ADAPTER_REPO,
        subfolder=subfolder,
        weight_name=weight,
        image_encoder_folder=IP_IMAGE_ENCODER,
        cache_dir=cache_dir,
    )
    pipeline.to(device)
    pipeline.vae.enable_tiling()
    pipeline.vae.enable_slicing()
    pipeline.set_progress_bar_config(disable=True)
    return pipeline, names


def set_ip_scale(pipeline, mode: str, scale: float) -> None:
    spec = IP_MODES[mode]
    if spec is None:
        pipeline.set_ip_adapter_scale(scale)
        return
    scaled = {
        section: {block: [v * scale for v in values] for block, values in blocks.items()}
        for section, blocks in spec.items()
    }
    pipeline.set_ip_adapter_scale(scaled)


def canny_image(aerial: Image.Image, low: int, high: int) -> Image.Image:
    g = cv2.cvtColor(np.array(aerial), cv2.COLOR_RGB2GRAY)
    g = cv2.GaussianBlur(g, (0, 0), 1.0)
    e = cv2.Canny(g, low, high)
    return Image.fromarray(np.stack([e, e, e], -1))


def depth_image(aerial: Image.Image) -> Image.Image:
    """Cheap relief proxy for a nadir aerial: the ControlNet wants a depth-ish map and we have
    no depth sensor, so use a smoothed luminance-inverse (tree canopies/shadows dark = 'far').
    Good enough to hold large shapes; the canny branch carries the precise edges."""
    g = cv2.cvtColor(np.array(aerial), cv2.COLOR_RGB2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 3.0)
    g = 255.0 * (g - g.min()) / max(1e-6, g.max() - g.min())
    d = g.astype(np.uint8)
    return Image.fromarray(np.stack([d, d, d], -1))


def control_images(names, aerial_work: Image.Image, canny_low: int, canny_high: int):
    out = []
    for n in names:
        if n == "tile":
            out.append(aerial_work)
        elif n == "canny":
            out.append(canny_image(aerial_work, canny_low, canny_high))
        elif n == "depth":
            out.append(depth_image(aerial_work))
    return out[0] if len(out) == 1 else out


def generate(pipeline, names, aerial, style_ref, *, strength, seed, steps, guidance, controlnet_scales,
             prompt, negative_prompt, work_scale, canny_low, canny_high):
    work_size = (WORK_SIZE[0] * work_scale, WORK_SIZE[1] * work_scale)
    card_size = (CARD_SIZE[0] * work_scale, CARD_SIZE[1] * work_scale)
    conditioning = aerial.resize(work_size, Image.LANCZOS)
    control = control_images(names, conditioning, canny_low, canny_high)
    scales = controlnet_scales[0] if len(names) == 1 else list(controlnet_scales)
    # CPU generator: reproducible on every backend; MPS seeds will not match CUDA seeds anyway.
    generator = torch.Generator(device="cpu").manual_seed(seed)
    result = pipeline(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=conditioning,
        control_image=control,
        ip_adapter_image=style_ref,
        strength=strength,
        num_inference_steps=steps,
        guidance_scale=guidance,
        controlnet_conditioning_scale=scales,
        generator=generator,
    ).images[0]
    return result.resize(card_size, Image.LANCZOS)


def measure_card(repo: Path, hole: int, aerial_path: Path, card_path: Path) -> dict:
    sys.path.insert(0, str(repo / "scripts" / "imagery"))
    import measure_drift as md  # noqa: E402

    geometry = md.load_geometry(repo / "public/course/peach-tree/sources.json", hole)
    result = md.measure(aerial_path, card_path, geometry, 150)
    result["pass"] = result["maxYards"] <= 5.0
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--repo", type=Path, default=Path.home() / "rex/peach-tree-golf-tracker")
    ap.add_argument("--aerial", type=Path, help="conditioning aerial; defaults to the repo's hole-NN.webp")
    ap.add_argument("--style-ref", type=Path, nargs="+", required=True, help="style reference image(s); each is its own run")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--control", choices=sorted(CONTROL_COMBOS), default="tile")
    ap.add_argument("--base", choices=sorted(BASES), default="sdxl", help="SDXL-family base checkpoint")
    ap.add_argument("--strength", type=float, nargs="+", default=[0.75])
    ap.add_argument("--controlnet-scale", type=float, nargs="+", default=[0.85],
                    help="scale(s) for the (first) ControlNet; each value is a run")
    ap.add_argument("--second-scale", type=float, default=0.6,
                    help="scale for the second ControlNet in a '+' combo (fixed per invocation)")
    ap.add_argument("--canny", type=int, nargs=2, default=[80, 180], metavar=("LOW", "HIGH"))
    ap.add_argument("--ip-scale", type=float, nargs="+", default=[0.8])
    ap.add_argument("--ip-mode", choices=sorted(IP_MODES), nargs="+", default=["style"])
    ap.add_argument("--adapter", choices=sorted(IP_ADAPTERS), default="vit-h")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="painted")
    ap.add_argument("--seed", type=int, default=20260726)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--work-scale", type=int, default=1, choices=[1, 2])
    ap.add_argument("--device", default="auto")
    ap.add_argument("--dtype", choices=["fp16", "fp32"], default="fp16")
    ap.add_argument("--cache-dir", type=Path, default=Path.home() / "rex/peach-tree-imagery/hf-cache/hub")
    ap.add_argument("--measure", action="store_true", help="run the repo's measure_drift on every output")
    ap.add_argument("--measure-against", type=Path,
                    help="aerial to measure drift against; defaults to the repo's REAL hole-NN.webp even when "
                         "--aerial is a recoloured conditioning image (drift is always against the truth)")
    ap.add_argument("--tag", default="", help="extra filename tag (use --tag=-x form if it starts with a dash)")
    args = ap.parse_args()

    device = pick_device(args.device)
    dtype = torch.float16 if args.dtype == "fp16" else torch.float32
    true_aerial = args.repo / f"public/course/peach-tree/hole-{args.hole:02d}.webp"
    aerial_path = args.aerial or true_aerial
    measure_against = args.measure_against or true_aerial
    aerial = Image.open(aerial_path).convert("RGB")
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"device {device} dtype {args.dtype} | control {args.control} | loading SDXL + IP-Adapter {args.adapter} from {args.cache_dir}", flush=True)
    t0 = time.time()
    pipeline, names = load_pipeline(device, args.cache_dir, args.adapter, dtype, args.control, BASES[args.base])
    print(f"loaded in {time.time() - t0:.0f}s", flush=True)

    prompt, negative_prompt = PROMPTS[args.prompt]
    combos = [
        (ref, mode, ip_scale, strength, cn)
        for ref in args.style_ref
        for mode in args.ip_mode
        for ip_scale in args.ip_scale
        for cn in args.controlnet_scale
        for strength in args.strength
    ]
    print(f"{len(combos)} cards to generate", flush=True)
    for ref_path, mode, ip_scale, strength, cn in combos:
        style_ref = Image.open(ref_path).convert("RGB")
        set_ip_scale(pipeline, mode, ip_scale)
        scales = [cn] + [args.second_scale] * (len(names) - 1)
        started = time.time()
        image = generate(
            pipeline, names, aerial, style_ref,
            strength=strength, seed=args.seed, steps=args.steps, guidance=args.guidance,
            controlnet_scales=scales, prompt=prompt, negative_prompt=negative_prompt,
            work_scale=args.work_scale, canny_low=args.canny[0], canny_high=args.canny[1],
        )
        ref_tag = ref_path.stem.replace("hole-", "ref").replace("-illustrated", "").replace("-original", "")
        scale_tag = "" if args.work_scale == 1 else f"-x{args.work_scale}"
        ctl_tag = args.control.replace("+", "_")
        second_tag = "" if len(names) == 1 else f"-c2_{args.second_scale:.2f}"
        stem = (
            f"hole-{args.hole:02d}-styled-{ref_tag}-{ctl_tag}-{mode}-ip{ip_scale:.2f}"
            f"-s{strength:.2f}-c{cn:.2f}{second_tag}-{args.prompt}-g{args.guidance:.1f}-{args.adapter}-{args.base}{scale_tag}{args.tag}"
        ).replace(".", "_")
        image_path = args.out / f"{stem}.png"
        image.save(image_path)
        seconds = round(time.time() - started, 1)
        sidecar = {
            "hole": args.hole,
            "aerial": str(aerial_path),
            "styleRef": str(ref_path),
            "baseModel": BASES[args.base],
            "base": args.base,
            "vae": VAE_FIX,
            "control": args.control,
            "controlnets": [CONTROLNETS[n] for n in names],
            "controlnetConditioningScale": cn,
            "controlnetScales": scales,
            "canny": args.canny if "canny" in names else None,
            "ipAdapter": f"{IP_ADAPTER_REPO}/{IP_ADAPTERS[args.adapter][0]}/{IP_ADAPTERS[args.adapter][1]}",
            "adapter": args.adapter,
            "ipMode": mode,
            "ipScale": ip_scale,
            "strength": strength,
            "seed": args.seed,
            "steps": args.steps,
            "guidance": args.guidance,
            "promptFamily": args.prompt,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "workSize": [d * args.work_scale for d in WORK_SIZE],
            "cardSize": [d * args.work_scale for d in CARD_SIZE],
            "workScale": args.work_scale,
            "device": device,
            "dtype": args.dtype,
            "torch": torch.__version__,
            "machine": platform.node(),
            "secondsTaken": seconds,
        }
        line = (f"  {args.control:10s} {mode:12s} ip {ip_scale:.2f} s {strength:.2f} c {cn:.2f} ref {ref_tag:6s} "
                f"-> {image_path.name} ({seconds:.0f}s)")
        if args.measure:
            drift = measure_card(args.repo, args.hole, measure_against, image_path)
            drift["measuredAgainst"] = str(measure_against)
            sidecar["drift"] = drift
            line += f"  drift max {drift['maxYards']:.2f} yd median {drift['medianYards']:.2f} yd {'PASS' if drift['pass'] else 'FAIL'}"
        (args.out / f"{stem}.json").write_text(json.dumps(sidecar, indent=2, default=float) + "\n")
        print(line, flush=True)


if __name__ == "__main__":
    main()
